"""Hosting-independent correctness fixes: the visitor's clock, atomic recurring
completion, race-free conflict inserts, the health storage lock, and
stdout logging.

Each of these is wrong on any host but becomes *visible* on AWS: Lambda's
clock is UTC, and concurrent requests are the normal case rather than a
double-click away.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from api import clock as clock_module
from api.clock import CLIENT_NOW_HEADER, ClientClock
from api.repositories.base import KIND_DEMO, OwnerRecord
from api.services.scheduler_service import SchedulerService
from conftest import repo_for
from storage_backends import dynamodb_is_mocked, selected_storage
from pawpal_ai import logging_setup
from pawpal_ai.config import get_settings
from pawpal_ai.health_models import Conflict, HealthRecord, RecordType, ReviewStatus
from pawpal_ai.storage import conflict_id_for, init_db as init_health_db
from pawpal_system import Category, Frequency, Task

REPO_ROOT = Path(__file__).resolve().parent.parent

# 21:00 on Tuesday 15 September in Chicago (UTC-5) is 02:00 on Wednesday the
# 16th in UTC -- the evening hours where the server's date and the visitor's
# date disagree.
SERVER_UTC_NOW = datetime(2026, 9, 16, 2, 0)
VISITOR_NOW = "2026-09-15T21:00:00"


@pytest.fixture
def health_storage(tmp_path):
    """pawpal_ai's standalone Storage -- the library's own persistence, still
    used outside the API (tests, scripts), and still shared across threads."""
    storage = init_health_db(tmp_path / "library.db")
    yield storage
    storage.close()


@pytest.fixture
def repo(backend):
    """The API's repository for one demo owner."""
    owner = OwnerRecord(owner_id="demo_test", kind=KIND_DEMO, expires_at=None)
    backend.create_owner(owner)
    return backend.for_owner(owner)


@pytest.fixture
def client(make_client, monkeypatch):
    monkeypatch.setattr(clock_module, "_utcnow_naive", lambda: SERVER_UTC_NOW)
    return make_client()


def _pet(client) -> str:
    resp = client.post("/api/pets", json={"name": "Max", "pet_type": "dog", "age": 3})
    assert resp.status_code == 201, resp.text
    return resp.json()["pet_id"]


# -- the visitor's clock ---------------------------------------------------------


class TestClientClock:
    def test_uses_a_plausible_header_and_derives_the_offset(self):
        c = ClientClock.from_header(VISITOR_NOW, server_utc_now=SERVER_UTC_NOW)
        assert c.now == datetime(2026, 9, 15, 21, 0)
        assert c.today == date(2026, 9, 15)
        assert c.utc_offset == timedelta(hours=-5)

    def test_offset_is_rounded_to_the_quarter_hour(self):
        # A browser clock a couple of minutes off still lands on India's +05:30.
        c = ClientClock.from_header("2026-09-16T07:32:10", server_utc_now=SERVER_UTC_NOW)
        assert c.utc_offset == timedelta(hours=5, minutes=30)

    @pytest.mark.parametrize(
        "raw",
        [None, "", "not a date", "2026-09-15T21:00:00Z", "2026-09-10T21:00:00"],
        ids=["missing", "empty", "garbage", "has-timezone", "days-off"],
    )
    def test_falls_back_to_the_server_clock(self, raw):
        c = ClientClock.from_header(raw, server_utc_now=SERVER_UTC_NOW)
        assert c.now == SERVER_UTC_NOW
        assert c.utc_offset is None

    def test_to_local_converts_aware_datetimes_with_the_visitors_offset(self):
        c = ClientClock.from_header(VISITOR_NOW, server_utc_now=SERVER_UTC_NOW)
        aware = datetime.fromisoformat("2026-09-16T02:00:00+00:00")
        assert c.to_local(aware) == datetime(2026, 9, 15, 21, 0)
        naive = datetime(2026, 9, 15, 8, 0)
        assert c.to_local(naive) is naive


class TestVisitorTodayIsUsed:
    def test_task_without_due_date_is_due_on_the_visitors_day(self, client):
        resp = client.post(
            "/api/tasks",
            json={"name": "Walk", "category": "exercise", "duration": 30},
            headers={CLIENT_NOW_HEADER: VISITOR_NOW},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["due_date"].startswith("2026-09-15T21:00")

    def test_utc_due_date_is_stored_as_the_visitors_wall_clock_time(self, client):
        pet_id = _pet(client)
        resp = client.post(
            "/api/tasks",
            json={
                "name": "Walk",
                "category": "exercise",
                "duration": 30,
                "pet_id": pet_id,
                "frequency": "weekly",
                "due_date": "2026-09-16T02:00:00Z",
                "end_date": "2026-12-01T00:00:00",
            },
            headers={CLIENT_NOW_HEADER: VISITOR_NOW},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["due_date"] == "2026-09-15T21:00:00"
        # A naive end_date next to an aware due_date used to make
        # Task.has_ended raise TypeError on completion.
        done = client.post(f"/api/tasks/{resp.json()['task_id']}/complete")
        assert done.status_code == 200, done.text

    def test_schedule_defaults_to_the_visitors_today(self, client):
        pet_id = _pet(client)
        # Weekly on Tuesdays. The visitor's today is Tuesday 15th; the
        # server's UTC date is already Wednesday 16th.
        client.post(
            "/api/tasks",
            json={
                "name": "Brush",
                "category": "grooming",
                "duration": 15,
                "pet_id": pet_id,
                "frequency": "weekly",
                "due_date": "2026-09-08T08:00:00",
            },
        )
        with_header = client.post("/api/schedule/generate", headers={CLIENT_NOW_HEADER: VISITOR_NOW})
        assert [i["task"]["name"] for i in with_header.json()["schedule"]] == ["Brush"]
        assert with_header.json()["schedule"][0]["start"].startswith("2026-09-15")

        # Without the header the server clock is the only clock there is.
        without = client.post("/api/schedule/generate")
        assert without.json()["schedule"] == []

    def test_explicit_schedule_date_still_wins(self, client):
        resp = client.post(
            "/api/schedule/generate", params={"date": "2026-10-01"}, headers={CLIENT_NOW_HEADER: VISITOR_NOW}
        )
        assert resp.status_code == 200

    def test_schedule_care_status_uses_the_visitors_today(self, client, backend):
        pet_id = _pet(client)
        record = HealthRecord(
            record_id="rec_due_today",
            pet_id=pet_id,
            record_type=RecordType.VACCINATION,
            fields={"vaccine_name": "Rabies", "due_date": "2026-09-15"},
            review_status=ReviewStatus.APPROVED,
        )
        repo_for(backend, client).save_record(record)

        local = client.post(
            f"/api/health/pets/{pet_id}/schedule-care", headers={CLIENT_NOW_HEADER: VISITOR_NOW}
        ).json()
        assert local["reminders"][0]["care_status"] == "due_soon"

        # By the server's UTC date the same vaccine is already a day overdue.
        server = client.post(f"/api/health/pets/{pet_id}/schedule-care").json()
        assert server["reminders"][0]["care_status"] == "overdue"


# -- atomic recurring completion --------------------------------------------------


def _daily_task(repo) -> str:
    task = Task(
        name="Feed",
        category=Category.FEEDING,
        pet_id="",
        duration=10,
        frequency=Frequency.DAILY,
        due_date=datetime(2026, 9, 15, 8, 0),
    )
    repo.create_task(task)
    return task.id


class TestAtomicCompletion:
    def test_repeated_completion_creates_one_next_occurrence(self, repo):
        service = SchedulerService(repo)
        task_id = _daily_task(repo)

        first = service.complete_task(task_id)
        second = service.complete_task(task_id)

        assert first.next_occurrence is not None
        assert second.task.completed is True
        assert second.next_occurrence is None
        assert len(repo.list_tasks()) == 2

    def test_concurrent_completion_creates_one_next_occurrence(self, repo):
        if selected_storage() == "dynamodb" and dynamodb_is_mocked():
            pytest.skip("moto does not serialize concurrent transactions; see "
                        "test_repository_contract.py::test_completion_is_one_conditional_transaction")
        task_id = _daily_task(repo)
        threads_n = 8
        barrier = threading.Barrier(threads_n)
        results, errors = [], []

        def complete():
            # Each request builds its own service over the one shared backend,
            # exactly as api/deps.py does.
            service = SchedulerService(repo)
            barrier.wait()
            try:
                results.append(service.complete_task(task_id))
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=complete) for _ in range(threads_n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert sum(1 for r in results if r.next_occurrence is not None) == 1
        rows = repo.list_tasks()
        assert len(rows) == 2
        assert sorted(bool(r["completed"]) for r in rows) == [False, True]

    def test_storage_completion_writes_nothing_when_already_completed(self, repo):
        task_id = _daily_task(repo)
        nxt = Task(name="Feed", category=Category.FEEDING, pet_id="", duration=10)
        assert repo.complete_task(task_id, None) is True
        assert repo.complete_task(task_id, nxt) is False
        assert repo.get_task(nxt.id) is None

    def test_completing_a_missing_task_writes_nothing(self, repo):
        nxt = Task(name="Feed", category=Category.FEEDING, pet_id="", duration=10)
        assert repo.complete_task("nope", nxt) is False
        assert repo.get_task(nxt.id) is None


# -- conflicts and the health storage lock -----------------------------------------


def _conflict(value_a="2026-03-01", value_b="2026-06-15") -> Conflict:
    return Conflict(
        pet_id="p1", record_type=RecordType.VACCINATION, field="due_date", value_a=value_a, value_b=value_b
    )


class TestConflictInsertIfAbsent:
    def test_same_conflict_in_either_order_is_stored_once(self, health_storage):
        assert health_storage.save_conflict_if_absent(_conflict()) is not None
        assert health_storage.save_conflict_if_absent(_conflict()) is None
        assert health_storage.save_conflict_if_absent(_conflict("2026-06-15", "2026-03-01")) is None
        assert len(health_storage.list_conflicts("p1")) == 1

    def test_id_is_order_independent(self):
        assert conflict_id_for(_conflict()) == conflict_id_for(_conflict("2026-06-15", "2026-03-01"))
        assert conflict_id_for(_conflict()) != conflict_id_for(_conflict(value_b="2026-06-16"))

    def test_resolved_conflict_is_not_reopened(self, health_storage):
        conflict_id = health_storage.save_conflict_if_absent(_conflict())
        health_storage.resolve_conflict(conflict_id)
        health_storage.save_conflict_if_absent(_conflict())
        assert health_storage.get_conflict(conflict_id)["resolved"] == 1

    def test_legacy_random_id_row_still_dedupes(self, health_storage):
        health_storage.save_conflict(_conflict())  # random id, as rows written before this change
        assert health_storage.save_conflict_if_absent(_conflict("2026-06-15", "2026-03-01")) is None
        assert len(health_storage.list_conflicts("p1")) == 1

    def test_concurrent_inserts_store_one_row(self, health_storage):
        barrier = threading.Barrier(8)

        def insert():
            barrier.wait()
            health_storage.save_conflict_if_absent(_conflict())

        threads = [threading.Thread(target=insert) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(health_storage.list_conflicts("p1")) == 1


class TestHealthStorageLock:
    def test_concurrent_writes_and_reads_do_not_interleave(self, health_storage):
        errors = []

        def work(worker: int):
            try:
                for i in range(25):
                    rec = HealthRecord(
                        record_id=f"rec_{worker}_{i}",
                        pet_id="p1",
                        record_type=RecordType.MEDICATION,
                        fields={"medication_name": "Amoxicillin"},
                    )
                    health_storage.save_record(rec, document_id="doc_1")
                    assert health_storage.get_record(rec.record_id) is not None
                    health_storage.list_records("p1")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(w,)) for w in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        assert len(health_storage.list_records("p1")) == 150

    def test_record_document_id_lookup(self, health_storage):
        rec = HealthRecord(record_id="rec_1", pet_id="p1", record_type=RecordType.VACCINATION)
        health_storage.save_record(rec, document_id="doc_9")
        assert health_storage.get_record_document_id("rec_1") == "doc_9"
        assert health_storage.get_record_document_id("missing") is None


def test_api_layer_never_reaches_into_a_private_sqlite_connection():
    """The services and routers go through storage methods. A `._conn` there is
    a query that a non-SQLite backend could never answer."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "api").rglob("*.py")
        if "._conn" in path.read_text(encoding="utf-8") and "repositories" not in path.parts
    ]
    assert offenders == []


# -- logging -------------------------------------------------------------------------


class TestLogDestination:
    def test_defaults_to_file_locally(self, monkeypatch):
        monkeypatch.delenv("PAWPAL_LOG_DESTINATION", raising=False)
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        assert get_settings().log_destination == "file"

    def test_defaults_to_stdout_on_lambda(self, monkeypatch):
        monkeypatch.delenv("PAWPAL_LOG_DESTINATION", raising=False)
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "pawpal-api")
        assert get_settings().log_destination == "stdout"

    def test_explicit_setting_wins(self, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "pawpal-api")
        monkeypatch.setenv("PAWPAL_LOG_DESTINATION", "file")
        assert get_settings().log_destination == "file"

    def test_stdout_handler_writes_redacted_json_lines(self, capsys):
        handler = logging_setup._build_handler("stdout", lambda: pytest.fail("no file for stdout"))
        handler.setFormatter(logging_setup.JsonLineFormatter())
        logger = logging.getLogger("pawpal_ai.test_stdout")
        logger.propagate = False
        logger.addHandler(handler)
        try:
            logger.info("record_saved", extra={"fields": {"record_id": "rec_1", "notes": "private"}})
        finally:
            logger.removeHandler(handler)
        out = capsys.readouterr().out
        assert '"record_id": "rec_1"' in out
        assert "private" not in out

    def test_file_handler_is_still_the_local_default(self, tmp_path):
        handler = logging_setup._build_handler("file", lambda: tmp_path / "app.log")
        try:
            assert isinstance(handler, logging.handlers.RotatingFileHandler)
        finally:
            handler.close()

    def test_chroma_path_setting_is_gone(self):
        assert not hasattr(get_settings(), "chroma_path")
