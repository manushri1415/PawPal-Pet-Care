"""Build api/demo/seed.json -- the sandbox every new demo visitor starts from.

Runs the real PawPal services end to end against a throwaway in-memory
database, exactly as a visitor's clicks would:

1. the owner routine, three pets and a week's worth of routine tasks through
   SchedulerService (including a completed task and two that overlap);
2. four vet documents -- data/demo_documents/, adapted from the fixtures in
   data/sample_documents/ -- through HealthService extraction, i.e. the real
   ingest -> chunk -> retrieve -> extract -> evidence-check pipeline with the
   free rule-based MockLLM;
3. human review (most records approved, one left pending), then schedule-care,
   which produces the reminders and the rabies-date conflict between Max's two
   clinics.

The resulting owner is exported as a snapshot. api/demo/seed.py replays it for
each visitor with fresh ids and every date moved from ANCHOR to the visitor's
today, which is why the documents are written with ``{{T+20}}``-style dates
relative to that anchor.

    python scripts/build_demo_seed.py

Rerun it whenever the pipeline, the schema or the documents change; the tests
in tests/test_demo_seed.py check the committed file is still consistent.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pawpal_ai.config import get_settings  # noqa: E402
from pawpal_ai.health_models import RecordType, ReviewStatus  # noqa: E402
from pawpal_ai.llm import MockLLM  # noqa: E402
from pawpal_system import Category, Frequency, Gender, Priority  # noqa: E402

from api.clock import ClientClock  # noqa: E402
from api.demo.seed import SEED_PATH  # noqa: E402
from api.repositories.base import KIND_DEMO, OwnerRecord  # noqa: E402
from api.repositories.sqlite import SqliteBackend  # noqa: E402
from api.schemas.scheduler import OwnerUpdate, PetCreate, TaskCreate  # noqa: E402
from api.services.health_service import HealthService  # noqa: E402
from api.services.scheduler_service import SchedulerService  # noqa: E402

ANCHOR = date(2026, 1, 1)
DOCUMENTS = REPO_ROOT / "data" / "demo_documents"
_PLACEHOLDER = re.compile(r"\{\{T([+-]\d+)\}\}")


def _at(days: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime.combine(ANCHOR + timedelta(days=days), time(hh, mm))


def _document(name: str) -> str:
    text = (DOCUMENTS / name).read_text(encoding="utf-8")
    return _PLACEHOLDER.sub(lambda m: (ANCHOR + timedelta(days=int(m.group(1)))).isoformat(), text)


def build() -> dict:
    backend = SqliteBackend(":memory:")
    owner = OwnerRecord(owner_id="seed", kind=KIND_DEMO, expires_at=None)
    backend.create_owner(owner)
    repo = backend.for_owner(owner)
    clock = ClientClock(now=_at(0, 9, 0), utc_offset=None)
    scheduler = SchedulerService(repo)
    health = HealthService(repo, MockLLM(), get_settings())

    scheduler.update_owner(
        OwnerUpdate(
            name="Alex",
            available_hours_per_day=3,
            work_start_hour=7,
            work_start_minute=0,
            work_end_hour=20,
            work_end_minute=0,
            break_between_tasks_minutes=10,
        )
    )

    max_id = scheduler.create_pet(
        PetCreate(name="Max", pet_type="dog", age=4, gender=Gender.MALE, color="golden")
    ).pet_id
    bella_id = scheduler.create_pet(
        PetCreate(name="Bella", pet_type="dog", age=6, gender=Gender.FEMALE, color="black and tan")
    ).pet_id
    luna_id = scheduler.create_pet(
        PetCreate(name="Luna", pet_type="cat", age=2, gender=Gender.FEMALE, color="gray")
    ).pet_id

    def task(pet_id, name, category, duration, priority, frequency, scheduled_time="", due=None, **extra):
        return scheduler.create_task(
            TaskCreate(
                name=name,
                category=category,
                pet_id=pet_id,
                duration=duration,
                priority=priority,
                frequency=frequency,
                scheduled_time=scheduled_time,
                due_date=due or _at(0, *(map(int, scheduled_time.split(":")) if scheduled_time else (9, 0))),
                **extra,
            ),
            clock,
        )

    task(max_id, "Breakfast", Category.FEEDING, 10, Priority.HIGH, Frequency.DAILY, "07:00")
    # Five minutes into Max's breakfast: the overlap warning has something to say.
    task(luna_id, "Breakfast", Category.FEEDING, 5, Priority.HIGH, Frequency.DAILY, "07:05")
    task(max_id, "Morning walk", Category.EXERCISE, 30, Priority.HIGH, Frequency.DAILY, "07:30")
    task(
        bella_id, "Amoxicillin with food", Category.MEDICATION, 5, Priority.HIGH, Frequency.DAILY, "08:00",
        notes="250mg twice a day, from the discharge sheet", end_date=_at(9, 23, 59),
    )
    task(bella_id, "Call the vet about the recheck", Category.MEDICAL, 15, Priority.MEDIUM, Frequency.ONCE, "07:45")
    task(luna_id, "Litter box", Category.OTHER, 10, Priority.MEDIUM, Frequency.DAILY, "18:30")
    task(max_id, "Flea and tick treatment", Category.MEDICATION, 5, Priority.MEDIUM, Frequency.MONTHLY, "20:00")
    task(bella_id, "Brush coat", Category.GROOMING, 20, Priority.MEDIUM, Frequency.WEEKLY)
    task(max_id, "Training: loose-leash walking", Category.TRAINING, 15, Priority.LOW, Frequency.DAILY)
    task(luna_id, "Wand toy play", Category.PLAY, 15, Priority.LOW, Frequency.DAILY)
    refill = task(luna_id, "Refill water fountain", Category.OTHER, 5, Priority.LOW, Frequency.ONCE, due=_at(-1, 17, 0))
    scheduler.complete_task(refill.task_id)

    extracted = {
        max_id: [
            health.extract_from_text(max_id, _document("max_happy_paws.txt")),
            health.extract_from_text(max_id, _document("max_downtown_rabies.txt")),
        ],
        bella_id: [health.extract_from_text(bella_id, _document("bella_discharge.txt"))],
        luna_id: [health.extract_from_text(luna_id, _document("luna_vaccine.txt"))],
    }
    for pet_id, responses in extracted.items():
        for response in responses:
            if response.result.fatal_error or not response.result.records:
                raise SystemExit(f"extraction produced nothing for {response.filename}: {response.result}")
            for record in response.result.records:
                # Luna's vaccine is left for the visitor to review.
                if pet_id != luna_id:
                    health.approve_record(record.record_id)

    for pet_id in (max_id, bella_id, luna_id):
        health.schedule_care(pet_id, today=ANCHOR)

    snapshot = backend.export_snapshot(owner.owner_id)
    _restamp(snapshot)
    _check(snapshot, max_id, luna_id)
    return {
        "anchor_date": ANCHOR.isoformat(),
        "generated_by": "scripts/build_demo_seed.py",
        "data": snapshot,
    }


def _restamp(snapshot: dict) -> None:
    """Replace wall-clock build timestamps with ones relative to ANCHOR.

    Rows keep their relative write order (one second apart), and land the
    evening before the anchor, so once moved to a visitor's today the sandbox
    history reads as "set up yesterday" rather than "in the future" or "the
    day this script was run".
    """
    base = datetime.combine(ANCHOR - timedelta(days=1), time(18, 0), tzinfo=timezone.utc)
    stamped = []
    for key in ("pets", "tasks", "documents", "chunks", "records", "reminders", "conflicts", "audit_log"):
        stamped.extend(snapshot.get(key, []))
    # A document's chunks share one timestamp; seq keeps them in order.
    stamped.sort(key=lambda row: (row["created_at"], row.get("seq", 0)))
    for i, row in enumerate(stamped):
        stamp = (base + timedelta(seconds=i)).isoformat(timespec="microseconds")
        row["created_at"] = stamp
        if "updated_at" in row:
            row["updated_at"] = stamp
    snapshot["profile"]["created_at"] = base.isoformat(timespec="microseconds")


def _check(snapshot: dict, max_id: str, luna_id: str) -> None:
    """Fail the build if the dataset stops demonstrating what it exists for."""
    records = snapshot["records"]
    assert any(r["review_status"] == ReviewStatus.PENDING.value for r in records), "no pending record"
    assert any(r["record_type"] == RecordType.MEDICATION.value for r in records), "no medication"
    assert all(json.loads(r["evidence_json"]) for r in records), "a record has no evidence"
    assert snapshot["reminders"], "no reminders"
    chunk_ids = {c["chunk_id"] for c in snapshot["chunks"]}
    for record in records:
        for evidence in json.loads(record["evidence_json"]).values():
            assert evidence["chunk_id"] in chunk_ids, "evidence cites a chunk that was not persisted"
    assert any(c["pet_id"] == max_id for c in snapshot["conflicts"]), "no conflict for Max"
    assert any(t["completed"] for t in snapshot["tasks"]), "no completed task"
    assert any(t["frequency"] != "once" for t in snapshot["tasks"]), "no recurring task"
    assert not any(r["pet_id"] == luna_id for r in snapshot["reminders"]), "Luna's undated vaccine got a reminder"


def main() -> int:
    seed = build()
    SEED_PATH.write_text(json.dumps(seed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    data = seed["data"]
    print(f"Wrote {SEED_PATH.relative_to(REPO_ROOT)}:")
    for key in ("pets", "tasks", "documents", "chunks", "records", "reminders", "conflicts", "audit_log"):
        print(f"  {key:<10} {len(data.get(key, []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
