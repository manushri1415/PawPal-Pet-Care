"""The storage contract, run against every backend.

Each test runs twice: on SQLite (local development, Docker) and on DynamoDB
through moto (production). The services are written against
api/repositories/base.py alone, so anything that differs between the two
backends -- an ordering, a missing cascade, a Decimal where an int belongs, a
lookup that is not owner-scoped -- is a bug that only production would show.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime

import pytest

from api.demo.seed import load_default_seeder
from api.repositories.base import KIND_DEMO, KIND_OWNER, OwnerRecord
from api.services.health_service import HealthService
from pawpal_ai.health_models import Conflict, HealthRecord, RecordType, Reminder, ReviewStatus, SourceEvidence
from pawpal_ai.llm import MockLLM
from pawpal_ai.vectorstore import Chunk
from pawpal_system import Category, Frequency, Gender, Pet, Priority, Task
from storage_backends import TABLE, reopen, storage_backend

EXPIRY = 2_000_000_000


@pytest.fixture(params=["sqlite", "dynamodb"])
def kind(request) -> str:
    return request.param


@pytest.fixture
def store(kind, tmp_path):
    with storage_backend(kind, tmp_path) as backend:
        yield backend


def _owner(store, owner_id="demo_alice", kind=KIND_DEMO, expires_at=EXPIRY):
    owner = OwnerRecord(owner_id, kind, expires_at if kind == KIND_DEMO else None)
    store.create_owner(owner)
    return store.for_owner(owner)


def _pet(repo, name="Max", **extra) -> str:
    pet = Pet(name=name, pet_type=extra.pop("pet_type", "dog"), age=extra.pop("age", 3), **extra)
    repo.create_pet(pet)
    return pet.id


def _task(repo, pet_id="", name="Walk", **extra) -> Task:
    task = Task(
        name=name,
        category=extra.pop("category", Category.EXERCISE),
        pet_id=pet_id,
        duration=extra.pop("duration", 30),
        due_date=extra.pop("due_date", datetime(2026, 9, 15, 8, 0)),
        **extra,
    )
    repo.create_task(task)
    return task


def _record(pet_id, record_id=None, status=ReviewStatus.PENDING, **fields) -> HealthRecord:
    return HealthRecord(
        record_id=record_id or "",
        pet_id=pet_id,
        record_type=RecordType.VACCINATION,
        fields={"vaccine_name": "Rabies", **fields},
        evidence={"vaccine_name": SourceEvidence(document_id="doc_1", chunk_id="doc_1#chunk-0", match_score=0.9)},
        confidence=0.875,
        review_status=status,
    )


# -- owners ---------------------------------------------------------------------------


class TestOwners:
    def test_create_is_insert_if_absent_and_get_round_trips(self, store):
        demo = OwnerRecord("demo_x", KIND_DEMO, EXPIRY)
        assert store.create_owner(demo) is True
        assert store.create_owner(demo) is False
        assert store.get_owner("demo_x") == demo
        assert store.get_owner("nobody") is None
        owner = OwnerRecord("owner", KIND_OWNER, None)
        store.create_owner(owner)
        assert store.get_owner("owner") == owner

    def test_delete_removes_everything_the_owner_has_and_nothing_else(self, store):
        alice, bob = _owner(store, "demo_alice"), _owner(store, "demo_bob")
        for repo in (alice, bob):
            pet = _pet(repo)
            _task(repo, pet)
            doc = repo.save_document(pet, "a.txt", "txt", 10)
            repo.save_chunks([Chunk(f"{doc}#chunk-0", doc, pet, "Rabies due 2030-01-01", "Vaccines")])
            repo.save_record(_record(pet), document_id=doc)
        store.delete_owner("demo_alice")

        assert store.get_owner("demo_alice") is None
        assert store.export_snapshot("demo_alice") == {
            "profile": None, "pets": [], "tasks": [], "documents": [], "chunks": [], "records": [],
            "reminders": [], "conflicts": [], "audit_log": [],
        }
        survivor = store.export_snapshot("demo_bob")
        assert survivor["profile"] and survivor["pets"] and survivor["chunks"] and survivor["records"]

    def test_purge_never_touches_live_sessions_or_the_owner_space(self, store):
        _owner(store, "demo_live", expires_at=EXPIRY)
        _owner(store, "owner", kind=KIND_OWNER)
        _owner(store, "demo_old", expires_at=100)
        store.purge_expired(now_epoch=1_000)
        assert store.get_owner("demo_live") is not None
        assert store.get_owner("owner") is not None
        # Expired owners stay readable as expired until cleanup (TTL on
        # DynamoDB) removes them; api/sessions.py treats them as gone either way.
        old = store.get_owner("demo_old")
        assert old is None or old.is_expired(1_000)


# -- profile ----------------------------------------------------------------------------


class TestProfile:
    def test_default_profile_and_partial_update(self, store):
        repo = _owner(store)
        profile = repo.get_profile()
        assert profile["name"] == "Pet Owner" and profile["kind"] == "demo" and profile["expires_at"] == EXPIRY
        updated = repo.update_profile(name="Alex", available_hours_per_day=2.5, not_a_column="x")
        assert updated["name"] == "Alex"
        assert updated["available_hours_per_day"] == 2.5
        assert isinstance(updated["available_hours_per_day"], float)
        assert isinstance(updated["work_start_hour"], int)
        assert "not_a_column" not in updated

    def test_owner_space_profile_never_expires(self, store):
        assert _owner(store, "owner", kind=KIND_OWNER).get_profile()["expires_at"] is None


# -- pets and tasks -----------------------------------------------------------------------


class TestPets:
    def test_crud_and_order(self, store):
        repo = _owner(store)
        first = _pet(repo, "Max", gender=Gender.MALE, color="golden")
        second = _pet(repo, "Luna", pet_type="cat", age=0, age_months=6)
        row = repo.get_pet(first)
        assert (row["name"], row["gender"], row["color"], row["age"]) == ("Max", "male", "golden", 3)
        assert isinstance(row["age"], int)
        assert [p["pet_id"] for p in repo.list_pets()] == [first, second]
        assert repo.update_pet(first, name="Maximus")["name"] == "Maximus"
        assert repo.update_pet("missing", name="x") is None
        assert repo.get_pet("missing") is None

    def test_delete_cascades_only_that_pets_tasks(self, store):
        repo = _owner(store)
        max_id, luna_id = _pet(repo, "Max"), _pet(repo, "Luna")
        max_task, luna_task, owner_task = _task(repo, max_id), _task(repo, luna_id), _task(repo, "")
        repo.save_record(_record(max_id))
        assert repo.delete_pet(max_id) is True
        assert repo.delete_pet(max_id) is False
        assert repo.get_task(max_task.id) is None
        assert repo.get_task(luna_task.id) is not None
        assert repo.get_task(owner_task.id) is not None
        # Health records stay (a forced delete orphans them, as before).
        assert repo.count_records(max_id) == 1


class TestTasks:
    def test_crud_filter_and_types(self, store):
        repo = _owner(store)
        pet = _pet(repo)
        a = _task(repo, pet, "Walk", priority=Priority.HIGH, frequency=Frequency.DAILY, scheduled_time="08:00")
        b = _task(repo, "", "Buy food", end_date=datetime(2026, 12, 1))
        row = repo.get_task(a.id)
        assert row["completed"] == 0 and isinstance(row["completed"], int)
        assert (row["priority"], row["frequency"], row["scheduled_time"]) == ("high", "daily", "08:00")
        assert row["due_date"] == "2026-09-15T08:00:00" and row["end_date"] is None
        assert repo.get_task(b.id)["pet_id"] is None
        assert [t["task_id"] for t in repo.list_tasks()] == [a.id, b.id]
        assert [t["task_id"] for t in repo.list_tasks(pet_id=pet)] == [a.id]

        moved = repo.update_task(a.id, pet_id=None, duration=45, completed=1)
        assert moved["pet_id"] is None and moved["duration"] == 45 and moved["completed"] == 1
        assert repo.update_task("missing", name="x") is None
        assert repo.delete_task(b.id) is True
        assert repo.delete_task(b.id) is False

    def test_completion_is_conditional_and_inserts_the_next_occurrence_once(self, store):
        repo = _owner(store)
        task = _task(repo, frequency=Frequency.DAILY)
        first_next = Task(name="Walk", category=Category.EXERCISE, pet_id="", duration=30)
        second_next = Task(name="Walk", category=Category.EXERCISE, pet_id="", duration=30)
        assert repo.complete_task(task.id, first_next) is True
        assert repo.complete_task(task.id, second_next) is False
        assert repo.get_task(task.id)["completed"] == 1
        assert repo.get_task(first_next.id) is not None
        assert repo.get_task(second_next.id) is None
        assert repo.complete_task("missing", None) is False

    def test_concurrent_completions_insert_one_next_occurrence(self, store, kind):
        if kind == "dynamodb":
            pytest.skip(
                "moto's in-memory DynamoDB does not serialize concurrent TransactWriteItems (two "
                "threads both pass the condition); real DynamoDB evaluates a transaction's conditions "
                "atomically. The DynamoDB side is covered by test_completion_is_one_conditional_transaction."
            )
        repo = _owner(store)
        task = _task(repo, frequency=Frequency.DAILY)
        barrier = threading.Barrier(6)
        wins, errors = [], []

        def complete():
            nxt = Task(name="Walk", category=Category.EXERCISE, pet_id="", duration=30)
            barrier.wait()
            try:
                if repo.complete_task(task.id, nxt):
                    wins.append(nxt.id)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=complete) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(wins) == 1
        assert len(repo.list_tasks()) == 2


# -- documents, chunks, records -----------------------------------------------------------------


class TestDocumentsAndChunks:
    def test_chunks_keep_saved_order_and_filter_by_pet_and_document(self, store):
        repo = _owner(store)
        d1 = repo.save_document("max", "one.txt", "txt", 100, injection_flagged=True)
        d2 = repo.save_document("max", "two.txt", "txt", 50, document_id="doc_fixed")
        assert d2 == "doc_fixed"
        # Twelve chunks: order must be numeric (chunk 10 after chunk 9), not lexicographic.
        one = [Chunk(f"{d1}#chunk-{i}", d1, "max", f"first {i}", f"s{i}") for i in range(12)]
        two = [Chunk(f"{d2}#chunk-{i}", d2, "max", f"second {i}", None) for i in range(2)]
        other_pet = [Chunk("doc_b#chunk-0", "doc_b", "bella", "bella", None)]
        repo.save_chunks(one)
        repo.save_chunks(two)
        repo.save_chunks(other_pet)
        assert repo.list_chunks("max") == one + two
        assert repo.list_chunks("max", document_id=d2) == two
        assert repo.list_chunks("bella") == other_pet
        assert repo.list_chunks("nobody") == []


class TestRecords:
    def test_save_get_list_count_review(self, store):
        repo = _owner(store)
        pending = _record("max", due_date="2030-01-01")
        approved = _record("max", status=ReviewStatus.APPROVED)
        repo.save_record(pending, document_id="doc_1")
        repo.save_record(approved)
        repo.save_record(_record("bella"))

        got = repo.get_record(pending.record_id)
        assert got == pending
        assert isinstance(got.confidence, float) and got.confidence == 0.875
        assert repo.get_record_document_id(pending.record_id) == "doc_1"
        assert repo.get_record_document_id(approved.record_id) == ""
        assert repo.get_record_document_id("missing") is None
        assert [r.record_id for r in repo.list_records("max")] == [pending.record_id, approved.record_id]
        assert [r.record_id for r in repo.list_records("max", ReviewStatus.APPROVED)] == [approved.record_id]
        assert repo.count_records("max") == 2 and repo.count_records("nobody") == 0

        repo.set_review_status(pending.record_id, ReviewStatus.REJECTED)
        assert repo.get_record(pending.record_id).review_status == ReviewStatus.REJECTED
        assert repo.get_record_document_id(pending.record_id) == "doc_1"

    def test_saving_an_existing_record_updates_it(self, store):
        repo = _owner(store)
        record = _record("max")
        repo.save_record(record, document_id="doc_1")
        record.fields["clinic"] = "Maple Vet"
        repo.save_record(record, document_id="doc_1")
        assert repo.get_record(record.record_id).fields["clinic"] == "Maple Vet"
        assert repo.count_records("max") == 1


class TestRemindersAndConflicts:
    def test_reminders_upsert_and_sort_by_due_date(self, store):
        repo = _owner(store)
        later = Reminder(reminder_id="rem_b", pet_id="max", record_id="b", record_type=RecordType.VACCINATION,
                         label="B", due_date=date(2030, 5, 1))
        sooner = Reminder(reminder_id="rem_a", pet_id="max", record_id="a", record_type=RecordType.APPOINTMENT,
                          label="A", due_date=date(2030, 1, 1),
                          source=SourceEvidence(document_id="d", chunk_id="d#chunk-0", supporting_text="due"))
        repo.save_reminder(later)
        repo.save_reminder(sooner)
        repo.save_reminder(later)
        listed = repo.list_reminders("max")
        assert [r.reminder_id for r in listed] == ["rem_a", "rem_b"]
        assert listed[0] == sooner
        assert repo.list_reminders("bella") == []

    def test_conflicts_insert_once_in_either_order_and_resolve(self, store):
        repo = _owner(store)
        conflict = Conflict(pet_id="max", record_type=RecordType.VACCINATION, field="due_date",
                            value_a="2030-01-01", value_b="2031-01-01")
        swapped = conflict.model_copy(update={"value_a": "2031-01-01", "value_b": "2030-01-01"})
        conflict_id = repo.save_conflict_if_absent(conflict)
        assert conflict_id
        assert repo.save_conflict_if_absent(conflict) is None
        assert repo.save_conflict_if_absent(swapped) is None
        assert [c["conflict_id"] for c in repo.list_conflicts("max")] == [conflict_id]

        repo.resolve_conflict(conflict_id)
        assert repo.get_conflict(conflict_id)["resolved"] == 1
        assert repo.list_conflicts("max", unresolved_only=True) == []
        assert repo.save_conflict_if_absent(conflict) is None  # stays resolved
        assert repo.get_conflict("missing") is None


class TestAudit:
    def test_newest_first_with_limit(self, store):
        repo = _owner(store)
        record = _record("max")
        repo.save_record(record)
        repo.set_review_status(record.record_id, ReviewStatus.APPROVED)
        repo.save_document("max", "a.txt", "txt", 10, document_id="doc_z")
        events = [a["event"] for a in repo.audit_trail()]
        assert events == ["document_saved", "record_approved", "record_saved"]
        assert [a["event"] for a in repo.audit_trail(limit=2)] == ["document_saved", "record_approved"]
        assert set(repo.audit_trail()[0]) == {"id", "event", "ref_id", "detail", "created_at"}


# -- isolation ---------------------------------------------------------------------------


class TestOwnerIsolation:
    def test_nothing_is_reachable_across_owners_by_id(self, store):
        alice, bob = _owner(store, "demo_alice"), _owner(store, "demo_bob")
        pet = _pet(alice)
        task = _task(alice, pet)
        doc = alice.save_document(pet, "a.txt", "txt", 10)
        alice.save_chunks([Chunk(f"{doc}#chunk-0", doc, pet, "text", None)])
        record = _record(pet)
        alice.save_record(record, document_id=doc)
        conflict_id = alice.save_conflict_if_absent(
            Conflict(pet_id=pet, record_type=RecordType.VACCINATION, field="due_date", value_a="1", value_b="2")
        )
        alice.save_reminder(Reminder(reminder_id="rem_x", pet_id=pet, record_id=record.record_id,
                                     record_type=RecordType.VACCINATION, label="x", due_date=date(2030, 1, 1)))

        assert bob.get_pet(pet) is None
        assert bob.update_pet(pet, name="pwned") is None
        assert bob.delete_pet(pet) is False
        assert bob.get_task(task.id) is None
        assert bob.update_task(task.id, name="pwned") is None
        assert bob.complete_task(task.id, None) is False
        assert bob.delete_task(task.id) is False
        assert bob.get_record(record.record_id) is None
        assert bob.get_record_document_id(record.record_id) is None
        assert bob.list_records(pet) == [] and bob.count_records(pet) == 0
        assert bob.list_chunks(pet) == []
        assert bob.list_reminders(pet) == []
        assert bob.get_conflict(conflict_id) is None and bob.list_conflicts(pet) == []
        assert bob.list_pets() == [] and bob.list_tasks() == []
        assert bob.audit_trail() == []

        bob.set_review_status(record.record_id, ReviewStatus.REJECTED)
        bob.resolve_conflict(conflict_id)
        assert alice.get_record(record.record_id).review_status == ReviewStatus.PENDING
        assert alice.get_conflict(conflict_id)["resolved"] == 0
        assert alice.get_pet(pet)["name"] == "Max"
        assert alice.get_task(task.id)["completed"] == 0


# -- snapshots and restarts ---------------------------------------------------------------------


class TestSnapshots:
    def test_export_import_round_trip(self, store):
        source = _owner(store, "demo_source")
        source.update_profile(name="Alex")
        pet = _pet(source)
        _task(source, pet)
        HealthService(source, MockLLM()).extract_from_text(
            pet, "Patient: Max\nRabies vaccine administered 2025-03-01. Next due 2026-03-01.\n"
        )
        exported = store.export_snapshot("demo_source")
        assert exported["chunks"] and exported["records"] and exported["audit_log"]

        # SQLite object ids are global primary keys (which is why the demo
        # seeder gives every copy fresh ids), so the verbatim snapshot is
        # re-imported only once its source is gone.
        store.delete_owner("demo_source")
        store.import_snapshot(OwnerRecord("demo_copy", KIND_DEMO, EXPIRY), exported)
        assert store.export_snapshot("demo_copy") == exported
        with pytest.raises(ValueError):
            store.import_snapshot(OwnerRecord("demo_copy", KIND_DEMO, EXPIRY), exported)

    def test_the_demo_seed_imports(self, store):
        owner = OwnerRecord("demo_seeded", KIND_DEMO, EXPIRY)
        load_default_seeder().seed(store, owner, date(2026, 9, 15))
        repo = store.for_owner(owner)
        assert sorted(p["name"] for p in repo.list_pets()) == ["Bella", "Luna", "Max"]
        assert len(repo.list_tasks()) == 11
        assert repo.get_profile()["name"] == "Alex"

    def test_ask_answers_the_same_from_a_reopened_backend(self, store, kind, tmp_path):
        repo = _owner(store, "demo_restart")
        service = HealthService(repo, MockLLM())
        service.extract_from_text("max", "Patient: Max\nRabies vaccine administered 2025-03-01. Next due 2026-03-01.\n")
        before = service.ask("max", "When is the rabies vaccine due?")
        assert before.citations

        reopened = reopen(kind, store, tmp_path)
        try:
            owner = reopened.get_owner("demo_restart")
            after = HealthService(reopened.for_owner(owner), MockLLM()).ask("max", "When is the rabies vaccine due?")
        finally:
            if kind == "sqlite":
                reopened.close()
        assert after == before


# -- DynamoDB specifics ----------------------------------------------------------------------------


@pytest.fixture
def dynamo(tmp_path):
    with storage_backend("dynamodb", tmp_path) as backend:
        yield backend


def _raw_items(backend, owner_id):
    resp = backend._client.query(
        TableName=TABLE,
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": {"S": f"OWNER#{owner_id}"}},
    )
    return resp["Items"]


class TestDynamoLayout:
    def _populate(self, repo):
        pet = _pet(repo)
        _task(repo, pet)
        HealthService(repo, MockLLM()).extract_from_text(
            pet, "Patient: Max\nRabies vaccine administered 2025-03-01. Next due 2026-03-01.\n"
        )
        record = repo.list_records(pet)[0]
        repo.set_review_status(record.record_id, ReviewStatus.APPROVED)
        repo.save_conflict_if_absent(
            Conflict(pet_id=pet, record_type=RecordType.VACCINATION, field="due_date", value_a="1", value_b="2")
        )
        repo.save_reminder(Reminder(reminder_id="rem_1", pet_id=pet, record_id=record.record_id,
                                    record_type=RecordType.VACCINATION, label="x", due_date=date(2030, 1, 1)))

    def test_every_demo_item_carries_the_session_ttl(self, dynamo):
        self._populate(_owner(dynamo, "demo_ttl", expires_at=EXPIRY))
        items = _raw_items(dynamo, "demo_ttl")
        prefixes = {item["SK"]["S"].split("#", 1)[0] for item in items}
        assert prefixes == {"PROFILE", "PET", "TASK", "DOC", "CHUNK", "REC", "REM", "CFT", "AUDIT"}
        assert all(item.get("expires_at") == {"N": str(EXPIRY)} for item in items)

    def test_owner_space_items_never_expire(self, dynamo):
        self._populate(_owner(dynamo, "owner", kind=KIND_OWNER))
        items = _raw_items(dynamo, "owner")
        assert items and all("expires_at" not in item for item in items)

    def test_keys_are_owner_scoped_and_chunks_sort_numerically(self, dynamo):
        repo = _owner(dynamo, "demo_keys")
        repo.save_chunks([Chunk(f"doc_k#chunk-{i}", "doc_k", "max", str(i), None) for i in range(11)])
        sks = sorted(i["SK"]["S"] for i in _raw_items(dynamo, "demo_keys") if i["SK"]["S"].startswith("CHUNK#"))
        assert sks[0] == "CHUNK#doc_k#00000" and sks[-1] == "CHUNK#doc_k#00010"

    def test_completion_is_one_conditional_transaction(self, dynamo):
        """What makes concurrent completion safe on DynamoDB: the "still open"
        check and the next occurrence's insert travel in ONE TransactWriteItems,
        which DynamoDB applies all-or-nothing with its conditions evaluated
        atomically -- so of two racing completions, exactly one commits."""
        repo = _owner(dynamo, "demo_tx")
        task = _task(repo, frequency=Frequency.DAILY)
        nxt = Task(name="Walk", category=Category.EXERCISE, pet_id="", duration=30)
        calls = []
        real = dynamo._client.transact_write_items

        def spy(**kwargs):
            calls.append(kwargs)
            return real(**kwargs)

        dynamo._client.transact_write_items = spy
        try:
            assert repo.complete_task(task.id, nxt) is True
        finally:
            dynamo._client.transact_write_items = real

        assert len(calls) == 1
        update, put = (op for op in calls[0]["TransactItems"])
        assert update["Update"]["Key"]["SK"] == {"S": f"TASK#{task.id}"}
        assert update["Update"]["ConditionExpression"] == "attribute_exists(SK) AND #completed = :zero"
        assert put["Put"]["Item"]["SK"] == {"S": f"TASK#{nxt.id}"}
        assert put["Put"]["ConditionExpression"] == "attribute_not_exists(SK)"

    def test_table_has_ttl_enabled_on_expires_at(self, dynamo):
        ttl = dynamo._client.describe_time_to_live(TableName=TABLE)["TimeToLiveDescription"]
        assert ttl["AttributeName"] == "expires_at"
        assert ttl["TimeToLiveStatus"] in {"ENABLED", "ENABLING"}
