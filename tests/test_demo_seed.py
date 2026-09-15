"""The seeded demo sandbox (api/demo/seed.json, built by scripts/build_demo_seed.py).

A new visitor's sandbox has to demonstrate the product -- pets and a routine
with recurring and overlapping tasks, extracted health records with evidence,
one waiting for review, reminders and an unresolved conflict -- and it has to
be *current*: seeded on a visitor's today, due dates are still ahead of them.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from api.clock import CLIENT_NOW_HEADER
from api.demo.seed import SEED_PATH, DemoSeeder, load_default_seeder
from api.repositories.rows import row_to_conflict
from pawpal_ai.storage import conflict_id_for

REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 9, 15)
NOW_HEADER = {CLIENT_NOW_HEADER: f"{TODAY.isoformat()}T09:30:00"}


@pytest.fixture
def seeder() -> DemoSeeder:
    seeder = load_default_seeder()
    assert seeder is not None, "api/demo/seed.json is missing -- run scripts/build_demo_seed.py"
    return seeder


@pytest.fixture
def visitor(make_client, seeder, monkeypatch):
    # Pin the server clock near the visitor's so the client-clock header is accepted.
    from api import clock as clock_module
    from datetime import datetime

    monkeypatch.setattr(clock_module, "_utcnow_naive", lambda: datetime(2026, 9, 15, 14, 30))
    return make_client(seeder=seeder, headers=NOW_HEADER)


def _pets(client) -> dict[str, dict]:
    return {p["name"]: p for p in client.get("/api/pets").json()}


class TestSeededSandbox:
    def test_pets_routine_and_tasks(self, visitor):
        assert set(_pets(visitor)) == {"Max", "Bella", "Luna"}
        owner = visitor.get("/api/owner").json()
        assert owner["name"] == "Alex"
        tasks = visitor.get("/api/tasks", params={"status": "all"}).json()
        assert {t["frequency"] for t in tasks} >= {"daily", "weekly", "monthly", "once"}
        assert any(t["completed"] for t in tasks)
        assert any(t["end_date"] for t in tasks)
        # Two breakfasts five minutes apart, and a vet call during the walk.
        assert len(visitor.get("/api/tasks/overlaps").json()["overlaps"]) >= 1

    def test_the_schedule_plans_today(self, visitor):
        body = visitor.post("/api/schedule/generate").json()
        assert len(body["schedule"]) >= 5
        assert all(item["start"].startswith(TODAY.isoformat()) for item in body["schedule"])

    def test_records_evidence_review_reminders_and_conflicts(self, visitor):
        pets = _pets(visitor)
        max_records = visitor.get(f"/api/health/pets/{pets['Max']['pet_id']}/records").json()
        assert {r["review_status"] for r in max_records} == {"approved"}
        for record in max_records:
            assert record["evidence"], record
            for evidence in record["evidence"].values():
                assert evidence["supporting_text"]

        luna_records = visitor.get(f"/api/health/pets/{pets['Luna']['pet_id']}/records").json()
        assert [r["review_status"] for r in luna_records] == ["pending"]

        bella = visitor.get(f"/api/health/pets/{pets['Bella']['pet_id']}/records").json()
        assert {r["record_type"] for r in bella} >= {"medication", "appointment"}

        conflicts = visitor.get(
            f"/api/health/pets/{pets['Max']['pet_id']}/conflicts", params={"unresolved_only": True}
        ).json()
        assert conflicts
        assert visitor.get("/api/health/audit").json()

    def test_due_dates_are_relative_to_the_visitors_today(self, visitor):
        pets = _pets(visitor)
        reminders = visitor.get(f"/api/health/pets/{pets['Max']['pet_id']}/reminders").json()
        # Distemper: due 20 days after the anchor in the source document. The
        # rabies reminder is withheld -- its two clinics disagree.
        labels = {r["label"]: r for r in reminders}
        distemper = next(r for label, r in labels.items() if "Distemper" in label)
        assert distemper["due_date"] == (TODAY + timedelta(days=20)).isoformat()
        assert distemper["care_status"] == "due_soon"
        assert not any("Rabies" in label for label in labels)

        bella_reminders = visitor.get(f"/api/health/pets/{pets['Bella']['pet_id']}/reminders").json()
        assert [r["due_date"] for r in bella_reminders] == [(TODAY + timedelta(days=6)).isoformat()]

        tasks = visitor.get("/api/tasks").json()
        assert any(t["due_date"].startswith(TODAY.isoformat()) for t in tasks)

    def test_schedule_care_on_the_seed_is_already_settled(self, visitor):
        """Recomputing reminders/conflicts over the seeded records adds nothing:
        the snapshot's conflict ids and reminder rows match what the live code
        derives, so the RemindersPanel's automatic recalculation on mount does
        not pile up duplicates."""
        pets = _pets(visitor)
        max_id = pets["Max"]["pet_id"]
        before = visitor.get(f"/api/health/pets/{max_id}/conflicts").json()
        after = visitor.post(f"/api/health/pets/{max_id}/schedule-care").json()
        assert len(after["conflicts"]) == len(before)
        assert {c["conflict_id"] for c in after["conflicts"]} == {c["conflict_id"] for c in before}


class TestSnapshotRewrite:
    def test_every_id_is_new_and_references_follow(self, seeder):
        original = json.loads(SEED_PATH.read_text(encoding="utf-8"))["data"]
        built = seeder.build(TODAY)
        for table, key in (("pets", "pet_id"), ("tasks", "task_id"), ("documents", "document_id"),
                           ("records", "record_id"), ("audit_log", "id")):
            assert not {r[key] for r in built[table]} & {r[key] for r in original[table]}, table

        document_ids = {d["document_id"] for d in built["documents"]}
        pet_ids = {p["pet_id"] for p in built["pets"]}
        for record in built["records"]:
            assert record["document_id"] in document_ids
            assert record["pet_id"] in pet_ids
            for evidence in json.loads(record["evidence_json"]).values():
                assert evidence["document_id"] == record["document_id"]
                assert evidence["chunk_id"].startswith(record["document_id"] + "#chunk-")
        record_ids = {r["record_id"] for r in built["records"]}
        for reminder in built["reminders"]:
            assert reminder["record_id"] in record_ids
            assert reminder["reminder_id"] == f"rem_{reminder['record_id']}"
        for task in built["tasks"]:
            assert task["pet_id"] in pet_ids

    def test_conflict_ids_match_the_live_derivation(self, seeder):
        built = seeder.build(TODAY)
        assert built["conflicts"]
        for row in built["conflicts"]:
            assert row["conflict_id"] == conflict_id_for(row_to_conflict(row))
        conflict_ids = {c["conflict_id"] for c in built["conflicts"]}
        detected = [a for a in built["audit_log"] if a["event"] == "contradiction_detected"]
        assert detected and all(a["ref_id"] in conflict_ids for a in detected)

    @pytest.mark.parametrize("today", [date(2026, 2, 28), date(2028, 2, 29), date(2031, 12, 31)])
    def test_dates_shift_consistently_for_any_today(self, seeder, today):
        built = seeder.build(today)
        for record in built["records"]:
            fields = json.loads(record["fields_json"])
            evidence = json.loads(record["evidence_json"])
            for name, value in fields.items():
                if value and name.endswith("_date") and name in evidence:
                    assert value in evidence[name]["supporting_text"], (name, value)
        assert all(date.fromisoformat(r["due_date"]) > today for r in built["reminders"])

    def test_two_builds_share_no_ids(self, seeder):
        a, b = seeder.build(TODAY), seeder.build(TODAY)
        assert not {r["record_id"] for r in a["records"]} & {r["record_id"] for r in b["records"]}


def test_committed_seed_matches_what_the_builder_produces():
    """A stale seed.json (the pipeline, schema or documents changed and nobody
    rebuilt it) fails here rather than surfacing as a subtly wrong demo."""
    spec = importlib.util.spec_from_file_location("build_demo_seed", REPO_ROOT / "scripts" / "build_demo_seed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fresh = module.build()["data"]
    committed = json.loads(SEED_PATH.read_text(encoding="utf-8"))["data"]

    def shape(data):
        return {
            "counts": {k: len(v) for k, v in data.items() if isinstance(v, list)},
            "pets": sorted(p["name"] for p in data["pets"]),
            "tasks": sorted((t["name"], t["frequency"], t["completed"]) for t in data["tasks"]),
            "records": sorted(
                (r["record_type"], r["review_status"], r["fields_json"]) for r in data["records"]
            ),
            "reminders": sorted((r["label"], r["due_date"]) for r in data["reminders"]),
            "conflicts": sorted((c["field"], c["value_a"], c["value_b"]) for c in data["conflicts"]),
            "profile": data["profile"],
        }

    assert shape(fresh) == shape(committed)
