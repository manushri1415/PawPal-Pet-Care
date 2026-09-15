"""Anonymous demo sessions, the persistent owner space, and the isolation
between them.

The isolation tests are the ones that matter: two visitors -- two
TestClients, two cookie jars -- each build up pets, tasks, records,
reminders, conflicts and an audit trail, and then each tries every by-id
endpoint with the *other's* ids. Every one of those must behave exactly as it
does for an id that never existed, and afterwards the victim's data must be
untouched.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from api import sessions
from api.demo.seed import load_default_seeder
from api.repositories.base import KIND_DEMO, KIND_OWNER, OwnerRecord
from api.repositories.sqlite import SqliteBackend
from conftest import repo_for
from storage_backends import selected_storage
from pawpal_ai.health_models import Conflict, HealthRecord, RecordType, ReviewStatus
from pawpal_ai.storage import init_db as init_legacy_health_db

OWNER_KEY = "owner-secret-for-tests"
OWNER = {"X-PawPal-Owner-Key": OWNER_KEY}


@pytest.fixture(autouse=True)
def owner_key(monkeypatch):
    monkeypatch.setenv("PAWPAL_OWNER_KEY", OWNER_KEY)
    monkeypatch.delenv("PAWPAL_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("PAWPAL_DEMO_TTL_HOURS", raising=False)


def _session_cookie(resp) -> str | None:
    for value in resp.headers.get_list("set-cookie"):
        if value.startswith(f"{sessions.SESSION_COOKIE}="):
            return value
    return None


def _token(cookie: str) -> str:
    return cookie.split(";", 1)[0].split("=", 1)[1]


# -- the session cookie -----------------------------------------------------------


class TestSessionCookie:
    def test_first_request_creates_a_demo_session(self, make_client):
        client = make_client()
        resp = client.get("/api/session")
        assert resp.status_code == 200
        body = resp.json()
        assert body["kind"] == "demo"
        assert body["expires_at"]

        cookie = _session_cookie(resp)
        assert cookie is not None
        attributes = [part.strip() for part in cookie.split(";")]
        assert "HttpOnly" in attributes
        assert "SameSite=Lax" in attributes
        assert "Path=/api" in attributes
        assert "Secure" not in attributes  # off unless PAWPAL_COOKIE_SECURE
        max_age = int(next(a for a in attributes if a.startswith("Max-Age=")).split("=")[1])
        assert 48 * 3600 - 60 <= max_age <= 48 * 3600
        # 32 bytes of url-safe randomness.
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", _token(cookie))

    def test_the_session_is_reused_and_not_reissued(self, make_client):
        client = make_client()
        first = client.get("/api/session")
        second = client.get("/api/session")
        assert _session_cookie(second) is None
        assert second.json() == first.json()

    def test_secure_attribute_in_production(self, make_client, monkeypatch):
        monkeypatch.setenv("PAWPAL_COOKIE_SECURE", "1")
        cookie = _session_cookie(make_client().get("/api/session"))
        assert "Secure" in [part.strip() for part in cookie.split(";")]

    def test_ttl_is_configurable(self, make_client, monkeypatch):
        monkeypatch.setenv("PAWPAL_DEMO_TTL_HOURS", "24")
        cookie = _session_cookie(make_client().get("/api/session"))
        assert "Max-Age=86400" in cookie or "Max-Age=86399" in cookie

    def test_an_error_response_still_delivers_the_new_session(self, make_client):
        client = make_client()
        resp = client.get("/api/pets/does-not-exist")
        assert resp.status_code == 404
        assert _session_cookie(resp) is not None
        # ...and the browser keeps it: the next request reuses that session.
        assert _session_cookie(client.get("/api/pets")) is None

    def test_a_forged_or_malformed_cookie_starts_a_fresh_session(self, make_client):
        client = make_client()
        for bogus in ("x", "owner", "../../etc", "A" * 43):
            resp = client.get("/api/session", headers={"Cookie": f"{sessions.SESSION_COOKIE}={bogus}"})
            assert resp.json()["kind"] == "demo"
            assert _token(_session_cookie(resp)) != bogus

    def test_owner_id_is_derived_from_the_token_not_equal_to_it(self, make_client):
        client = make_client()
        token = _token(_session_cookie(client.get("/api/session")))
        owner_id = client.get("/api/owner").json()["owner_id"]
        assert owner_id.startswith("demo_")
        assert token not in owner_id
        assert owner_id == sessions.demo_owner_id(token)

    def test_healthz_never_creates_a_session(self, make_client, backend):
        resp = make_client().get("/api/healthz")
        assert resp.status_code == 200
        assert _session_cookie(resp) is None


# -- isolation ------------------------------------------------------------------------


def _populate(client, backend, label: str) -> dict:
    """Give a visitor one of everything, and return the ids."""
    pet = client.post("/api/pets", json={"name": f"{label} pet", "pet_type": "dog", "age": 3}).json()
    other_pet = client.post("/api/pets", json={"name": f"{label} cat", "pet_type": "cat", "age": 1}).json()
    task = client.post(
        "/api/tasks",
        json={"name": f"{label} walk", "category": "exercise", "duration": 30, "pet_id": pet["pet_id"],
              "frequency": "daily", "scheduled_time": "08:00"},
    ).json()
    repo = repo_for(backend, client)
    record_id = repo.save_record(
        HealthRecord(
            pet_id=pet["pet_id"],
            record_type=RecordType.VACCINATION,
            fields={"vaccine_name": f"{label} rabies", "due_date": "2030-01-01"},
            review_status=ReviewStatus.PENDING,
        ),
        document_id=repo.save_document(pet["pet_id"], "note.txt", "txt", 40),
    )
    assert client.post(f"/api/health/records/{record_id}/approve").status_code == 200
    care = client.post(f"/api/health/pets/{pet['pet_id']}/schedule-care").json()
    assert len(care["reminders"]) == 1
    conflict_id = repo.save_conflict_if_absent(
        Conflict(pet_id=pet["pet_id"], record_type=RecordType.VACCINATION, field="due_date",
                 value_a="2030-01-01", value_b="2031-01-01")
    )
    return {
        "owner_id": repo.owner_id,
        "pet_id": pet["pet_id"],
        "other_pet_id": other_pet["pet_id"],
        "task_id": task["task_id"],
        "record_id": record_id,
        "reminder_id": care["reminders"][0]["reminder_id"],
        "conflict_id": conflict_id,
    }


def _attack(attacker, victim: dict, own: dict) -> list[tuple[str, int]]:
    """Every by-id request, with the victim's ids. Returns (request, status)."""
    pet, task, record, conflict = victim["pet_id"], victim["task_id"], victim["record_id"], victim["conflict_id"]
    calls = [
        ("GET pet", attacker.get(f"/api/pets/{pet}")),
        ("PATCH pet", attacker.patch(f"/api/pets/{pet}", json={"name": "pwned"})),
        ("DELETE pet", attacker.delete(f"/api/pets/{pet}?force=true")),
        ("GET task", attacker.get(f"/api/tasks/{task}")),
        ("PATCH task", attacker.patch(f"/api/tasks/{task}", json={"name": "pwned"})),
        ("complete task", attacker.post(f"/api/tasks/{task}/complete")),
        ("uncomplete task", attacker.post(f"/api/tasks/{task}/uncomplete")),
        ("DELETE task", attacker.delete(f"/api/tasks/{task}")),
        ("GET record", attacker.get(f"/api/health/records/{record}")),
        ("PATCH record", attacker.patch(f"/api/health/records/{record}", json={"fields": {"clinic": "pwned"}})),
        ("approve record", attacker.post(f"/api/health/records/{record}/approve")),
        ("reject record", attacker.post(f"/api/health/records/{record}/reject")),
        ("list records", attacker.get(f"/api/health/pets/{pet}/records")),
        ("list reminders", attacker.get(f"/api/health/pets/{pet}/reminders")),
        ("list conflicts", attacker.get(f"/api/health/pets/{pet}/conflicts")),
        ("schedule-care", attacker.post(f"/api/health/pets/{pet}/schedule-care")),
        ("resolve conflict", attacker.post(f"/api/health/conflicts/{conflict}/resolve")),
        ("extract into pet", attacker.post(
            f"/api/health/pets/{pet}/documents:extract",
            data={"text": "Rabies vaccine administered 2025-03-01. Next due 2026-03-01."})),
        ("ask about pet", attacker.post(f"/api/health/pets/{pet}/ask", json={"question": "When is rabies due?"})),
        # Attaching the victim's pet to the attacker's own task.
        ("create task on pet", attacker.post(
            "/api/tasks", json={"name": "x", "category": "other", "duration": 5, "pet_id": pet})),
        ("move task to pet", attacker.patch(f"/api/tasks/{own['task_id']}", json={"pet_id": pet})),
    ]
    return [(name, resp.status_code) for name, resp in calls]


class TestVisitorIsolation:
    @pytest.fixture
    def visitors(self, make_client, backend):
        alice, bob = make_client(), make_client()
        return alice, _populate(alice, backend, "alice"), bob, _populate(bob, backend, "bob")

    def test_the_two_visitors_are_different_owners(self, visitors):
        _, alice_ids, _, bob_ids = visitors
        assert alice_ids["owner_id"] != bob_ids["owner_id"]

    def test_every_by_id_request_with_another_visitors_ids_is_not_found(self, visitors):
        alice, alice_ids, bob, bob_ids = visitors
        results = _attack(bob, alice_ids, bob_ids)
        expected_422 = {"create task on pet", "move task to pet"}
        for name, status in results:
            assert status == (422 if name in expected_422 else 404), (name, status)

    def test_the_victims_data_is_untouched_afterwards(self, visitors):
        alice, alice_ids, bob, bob_ids = visitors
        _attack(bob, alice_ids, bob_ids)

        assert alice.get(f"/api/pets/{alice_ids['pet_id']}").json()["name"] == "alice pet"
        task = alice.get(f"/api/tasks/{alice_ids['task_id']}").json()
        assert task["name"] == "alice walk" and task["completed"] is False
        record = alice.get(f"/api/health/records/{alice_ids['record_id']}").json()
        assert record["review_status"] == "approved" and "clinic" not in record["fields"]
        conflicts = alice.get(f"/api/health/pets/{alice_ids['pet_id']}/conflicts").json()
        assert [c["resolved"] for c in conflicts] == [False]
        assert len(alice.get("/api/tasks", params={"status": "all"}).json()) == 1

    def test_lists_and_computed_views_only_show_your_own_data(self, visitors):
        alice, alice_ids, bob, bob_ids = visitors
        for client, mine, theirs in ((alice, alice_ids, bob_ids), (bob, bob_ids, alice_ids)):
            pet_ids = {p["pet_id"] for p in client.get("/api/pets").json()}
            assert pet_ids == {mine["pet_id"], mine["other_pet_id"]}
            task_ids = {t["task_id"] for t in client.get("/api/tasks", params={"status": "all"}).json()}
            assert task_ids == {mine["task_id"]}
            schedule = client.post("/api/schedule/generate").json()
            assert {i["task"]["task_id"] for i in schedule["schedule"]} == {mine["task_id"]}
            assert client.get("/api/tasks/overlaps").json()["overlaps"] == []

            audit_refs = {entry["ref_id"] for entry in client.get("/api/health/audit").json()}
            assert mine["record_id"] in audit_refs
            assert not audit_refs & {theirs["record_id"], theirs["reminder_id"], theirs["conflict_id"]}

    def test_the_owner_key_reaches_only_the_owner_space(self, make_client, visitors):
        alice, alice_ids, _, _ = visitors
        owner = make_client(headers=OWNER)
        owner_pet = owner.post("/api/pets", json={"name": "Owner's dog", "pet_type": "dog", "age": 5}).json()

        assert owner.get(f"/api/pets/{alice_ids['pet_id']}").status_code == 404
        assert owner.get(f"/api/health/records/{alice_ids['record_id']}").status_code == 404
        assert alice.get(f"/api/pets/{owner_pet['pet_id']}").status_code == 404
        assert owner_pet["pet_id"] not in {p["pet_id"] for p in alice.get("/api/pets").json()}
        # The owner-gated extraction route cannot write into a visitor's pet either.
        resp = owner.post(
            f"/api/health/pets/{alice_ids['pet_id']}/documents:extract",
            data={"text": "Rabies vaccine administered 2025-03-01. Next due 2026-03-01."},
        )
        assert resp.status_code == 404

    def test_seeded_sandboxes_share_no_ids(self, make_client, backend):
        seeder = load_default_seeder()
        assert seeder is not None, "api/demo/seed.json is missing -- run scripts/build_demo_seed.py"
        alice, bob = make_client(seeder=seeder), make_client(seeder=seeder)
        alice_pets = alice.get("/api/pets").json()
        bob_pets = bob.get("/api/pets").json()
        assert [p["name"] for p in alice_pets] == [p["name"] for p in bob_pets]
        assert not {p["pet_id"] for p in alice_pets} & {p["pet_id"] for p in bob_pets}

        alice_records = [r for p in alice_pets for r in alice.get(f"/api/health/pets/{p['pet_id']}/records").json()]
        assert alice_records
        for record in alice_records:
            assert bob.get(f"/api/health/records/{record['record_id']}").status_code == 404
        assert bob.post(f"/api/health/pets/{alice_pets[0]['pet_id']}/schedule-care").status_code == 404


# -- expiry -----------------------------------------------------------------------------


class TestExpiry:
    def test_an_expired_session_is_replaced_even_before_its_rows_are_deleted(
        self, make_client, backend, monkeypatch
    ):
        client = make_client()
        pet = client.post("/api/pets", json={"name": "Old", "pet_type": "dog", "age": 2}).json()
        old_owner = client.get("/api/owner").json()["owner_id"]

        # 49 hours later -- with cleanup disabled, so the old rows physically
        # remain, as they would while DynamoDB's TTL has not got to them yet.
        real_now = sessions._now_epoch()
        monkeypatch.setattr(sessions, "_now_epoch", lambda: real_now + 49 * 3600)
        monkeypatch.setattr(backend, "purge_expired", lambda now_epoch, limit=50: 0)

        resp = client.get("/api/pets")
        assert _session_cookie(resp) is not None
        assert resp.json() == []
        assert client.get(f"/api/pets/{pet['pet_id']}").status_code == 404
        assert client.get("/api/owner").json()["owner_id"] != old_owner
        assert backend.get_owner(old_owner) is not None  # still stored, but no longer served

    def test_purge_removes_only_expired_demo_owners(self, backend):
        now = 1_800_000_000
        expired = OwnerRecord("demo_expired", KIND_DEMO, now - 1)
        live = OwnerRecord("demo_live", KIND_DEMO, now + 3600)
        owner = OwnerRecord("owner", KIND_OWNER, None)
        for o in (expired, live, owner):
            backend.create_owner(o)
            backend.for_owner(o).save_record(HealthRecord(pet_id="p", record_type=RecordType.MEDICATION))

        if selected_storage() == "dynamodb":
            # DynamoDB's TTL does the physical deletion; purge is a no-op there.
            assert backend.purge_expired(now) == 0
            assert backend.get_owner("demo_expired").is_expired(now)
        else:
            assert backend.purge_expired(now) == 1
            assert backend.get_owner("demo_expired") is None
            assert backend.for_owner(expired).count_records("p") == 0
        assert backend.get_owner("demo_live") is not None
        assert backend.for_owner(owner).count_records("p") == 1


# -- the owner space ----------------------------------------------------------------------


class TestOwnerSpace:
    def test_a_valid_key_opens_the_non_expiring_owner_space(self, make_client, backend):
        resp = make_client(headers=OWNER).get("/api/session")
        assert resp.json()["kind"] == "owner" and resp.json()["expires_at"] is None
        assert _session_cookie(resp) is None
        assert backend.get_owner(sessions.OWNER_SPACE_ID).expires_at is None

    def test_owner_data_persists_across_clients(self, make_client):
        make_client(headers=OWNER).post("/api/pets", json={"name": "Keeper", "pet_type": "dog", "age": 9})
        names = [p["name"] for p in make_client(headers=OWNER).get("/api/pets").json()]
        assert names == ["Keeper"]

    @pytest.mark.parametrize("path", ["/api/session", "/api/pets", "/api/health/audit"])
    def test_a_wrong_key_is_refused_not_downgraded(self, make_client, path):
        resp = make_client(headers={"X-PawPal-Owner-Key": "wrong"}).get(path)
        assert resp.status_code == 401
        assert _session_cookie(resp) is None

    def test_no_owner_access_when_the_server_has_no_key(self, make_client, monkeypatch):
        monkeypatch.delenv("PAWPAL_OWNER_KEY")
        assert make_client(headers=OWNER).get("/api/session").status_code == 503
        # Demo visitors are unaffected.
        assert make_client().get("/api/session").json()["kind"] == "demo"


# -- reset ----------------------------------------------------------------------------------


class TestReset:
    def test_reset_restores_the_seed_for_this_visitor_only(self, make_client, backend):
        seeder = load_default_seeder()
        alice, bob = make_client(seeder=seeder), make_client(seeder=seeder)
        alice.post("/api/pets", json={"name": "Extra", "pet_type": "bird", "age": 1})
        bob.post("/api/pets", json={"name": "Bob's extra", "pet_type": "fish", "age": 1})
        alice_owner = alice.get("/api/owner").json()["owner_id"]
        old_ids = {p["pet_id"] for p in alice.get("/api/pets").json()}

        resp = alice.post("/api/session/reset")
        assert resp.status_code == 200 and resp.json()["kind"] == "demo"
        cookie = _session_cookie(resp)
        assert cookie is not None  # same session, renewed expiry

        pets = alice.get("/api/pets").json()
        assert sorted(p["name"] for p in pets) == ["Bella", "Luna", "Max"]
        assert not {p["pet_id"] for p in pets} & old_ids
        assert alice.get("/api/owner").json()["owner_id"] == alice_owner
        assert "Bob's extra" in [p["name"] for p in bob.get("/api/pets").json()]

    def test_reset_without_a_seed_empties_the_sandbox(self, make_client):
        client = make_client()
        client.post("/api/pets", json={"name": "Gone", "pet_type": "dog", "age": 1})
        assert client.post("/api/session/reset").status_code == 200
        assert client.get("/api/pets").json() == []

    def test_the_owner_space_cannot_be_reset(self, make_client):
        owner = make_client(headers=OWNER)
        owner.post("/api/pets", json={"name": "Real", "pet_type": "dog", "age": 1})
        assert owner.post("/api/session/reset").status_code == 403
        assert [p["name"] for p in owner.get("/api/pets").json()] == ["Real"]


# -- databases from before owner scoping -------------------------------------------------------


_PRE_SESSION_SCHEDULER_SCHEMA = """
CREATE TABLE owners (owner_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, phone_number TEXT,
  available_hours_per_day REAL NOT NULL, work_start_hour INTEGER NOT NULL, work_start_minute INTEGER NOT NULL,
  work_end_hour INTEGER NOT NULL, work_end_minute INTEGER NOT NULL, break_between_tasks_minutes INTEGER NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE pets (pet_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), name TEXT NOT NULL,
  pet_type TEXT NOT NULL, age INTEGER NOT NULL, age_months INTEGER NOT NULL DEFAULT 0, gender TEXT NOT NULL,
  color TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE tasks (task_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id),
  pet_id TEXT REFERENCES pets(pet_id) ON DELETE CASCADE, name TEXT NOT NULL, category TEXT NOT NULL,
  duration INTEGER NOT NULL, priority TEXT NOT NULL, frequency TEXT NOT NULL, notes TEXT, scheduled_time TEXT,
  due_date TEXT NOT NULL, end_date TEXT, completed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
INSERT INTO owners VALUES ('owner','Manu','','',4,8,0,18,0,15,'2026-09-01T10:00:00','2026-09-01T10:00:00');
INSERT INTO pets VALUES ('pet-1','owner','Biscuit','dog',3,0,'male','','2026-09-01T10:00:00','2026-09-01T10:00:00');
"""


class TestPreSessionDatabase:
    def test_existing_single_user_data_becomes_the_owner_space(self, tmp_path, make_client, monkeypatch):
        db = tmp_path / "old.db"
        conn = sqlite3.connect(db)
        conn.executescript(_PRE_SESSION_SCHEDULER_SCHEMA)
        conn.commit()
        conn.close()
        legacy = init_legacy_health_db(db)  # the pre-scoping health tables, no owner_id column
        legacy.save_record(HealthRecord(record_id="rec_old", pet_id="pet-1", record_type=RecordType.MEDICATION))
        legacy.close()

        migrated = SqliteBackend(db)
        try:
            owner = migrated.get_owner("owner")
            assert owner == OwnerRecord("owner", KIND_OWNER, None)
            repo = migrated.for_owner(owner)
            assert [p["name"] for p in repo.list_pets()] == ["Biscuit"]
            assert repo.get_record("rec_old") is not None

            demo = OwnerRecord("demo_x", KIND_DEMO, None)
            migrated.create_owner(demo)
            assert migrated.for_owner(demo).get_record("rec_old") is None
            assert migrated.for_owner(demo).list_pets() == []
        finally:
            migrated.close()

        # Reopening an already-migrated database is a no-op.
        SqliteBackend(db).close()
