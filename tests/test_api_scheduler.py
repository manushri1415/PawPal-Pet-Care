"""FastAPI TestClient tests for the scheduler API (owner/pets/tasks/schedule).

Each test gets an isolated SQLite file via tmp_path + app.dependency_overrides
-- never touches data/pawpal.db (see MIGRATION_PLAN.md §9).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.deps import get_health_storage, get_scheduler_storage
from api.main import app
from api.storage import SchedulerStorage
from pawpal_ai.health_models import HealthRecord, RecordType
from pawpal_ai.storage import init_db as init_health_db


@pytest.fixture
def storages(tmp_path):
    db_path = tmp_path / "test.db"
    scheduler_storage = SchedulerStorage(db_path)
    health_storage = init_health_db(db_path)
    yield scheduler_storage, health_storage
    scheduler_storage.close()
    health_storage.close()


@pytest.fixture
def client(storages):
    scheduler_storage, health_storage = storages
    app.dependency_overrides[get_scheduler_storage] = lambda: scheduler_storage
    app.dependency_overrides[get_health_storage] = lambda: health_storage
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_pet(client, name="Max", pet_type="dog", age=3, **extra):
    resp = client.post("/api/pets", json={"name": name, "pet_type": pet_type, "age": age, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["pet_id"]


def _create_task(client, pet_id=None, **overrides):
    payload = {"name": "Walk", "category": "exercise", "duration": 30, **overrides}
    if pet_id is not None:
        payload["pet_id"] = pet_id
    resp = client.post("/api/tasks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestOwner:
    def test_get_owner_creates_default_singleton(self, client):
        resp = client.get("/api/owner")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Pet Owner"
        assert body["work_start_hour"] == 8
        assert body["work_end_hour"] == 18

    def test_get_owner_is_idempotent(self, client):
        first = client.get("/api/owner").json()
        second = client.get("/api/owner").json()
        assert first["owner_id"] == second["owner_id"]

    def test_patch_owner_updates_only_given_fields(self, client):
        client.get("/api/owner")
        resp = client.patch("/api/owner", json={"name": "Alex", "available_hours_per_day": 3})
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Alex"
        assert body["available_hours_per_day"] == 3
        assert body["work_start_hour"] == 8  # untouched field preserved

    def test_patch_owner_rejects_invalid_work_hour(self, client):
        resp = client.patch("/api/owner", json={"work_start_hour": 25})
        assert resp.status_code == 422

    def test_patch_owner_rejects_non_positive_available_hours(self, client):
        resp = client.patch("/api/owner", json={"available_hours_per_day": 0})
        assert resp.status_code == 422


class TestPets:
    def test_create_and_get_pet(self, client):
        pet_id = _create_pet(client, name="Max")
        resp = client.get(f"/api/pets/{pet_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Max"
        assert resp.json()["pet_type"] == "dog"

    def test_create_pet_rejects_zero_age(self, client):
        resp = client.post(
            "/api/pets", json={"name": "Max", "pet_type": "dog", "age": 0, "age_months": 0}
        )
        assert resp.status_code == 422

    def test_get_unknown_pet_404(self, client):
        assert client.get("/api/pets/nonexistent").status_code == 404

    def test_list_pets(self, client):
        _create_pet(client, name="Max")
        _create_pet(client, name="Whiskers", pet_type="cat", age=2)
        resp = client.get("/api/pets")
        assert resp.status_code == 200
        names = {p["name"] for p in resp.json()}
        assert names == {"Max", "Whiskers"}

    def test_patch_pet_updates_only_given_fields(self, client):
        pet_id = _create_pet(client, name="Max")
        resp = client.patch(f"/api/pets/{pet_id}", json={"name": "Maximus"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Maximus"
        assert body["pet_type"] == "dog"  # untouched

    def test_patch_pet_rejects_invalid_age(self, client):
        pet_id = _create_pet(client, name="Max")
        resp = client.patch(f"/api/pets/{pet_id}", json={"age": 0, "age_months": 0})
        assert resp.status_code == 422

    def test_delete_pet(self, client):
        pet_id = _create_pet(client, name="Max")
        resp = client.delete(f"/api/pets/{pet_id}")
        assert resp.status_code == 204
        assert client.get(f"/api/pets/{pet_id}").status_code == 404

    def test_delete_unknown_pet_404(self, client):
        assert client.delete("/api/pets/nonexistent").status_code == 404

    def test_delete_pet_cascades_its_tasks(self, client):
        pet_id = _create_pet(client, name="Max")
        task = _create_task(client, pet_id=pet_id)
        client.delete(f"/api/pets/{pet_id}")
        assert client.get(f"/api/tasks/{task['task_id']}").status_code == 404

    def test_delete_pet_with_health_records_returns_409(self, client, storages):
        _, health_storage = storages
        pet_id = _create_pet(client, name="Max")
        health_storage.save_record(HealthRecord(pet_id=pet_id, record_type=RecordType.VACCINATION))

        resp = client.delete(f"/api/pets/{pet_id}")
        assert resp.status_code == 409
        assert "1 health record" in resp.json()["detail"]

    def test_delete_pet_with_force_bypasses_health_record_check(self, client, storages):
        _, health_storage = storages
        pet_id = _create_pet(client, name="Max")
        health_storage.save_record(HealthRecord(pet_id=pet_id, record_type=RecordType.VACCINATION))

        resp = client.delete(f"/api/pets/{pet_id}?force=true")
        assert resp.status_code == 204


class TestTasks:
    def test_create_task_for_pet(self, client):
        pet_id = _create_pet(client)
        task = _create_task(client, pet_id=pet_id, name="Morning walk", priority="high")
        assert task["name"] == "Morning walk"
        assert task["completed"] is False
        assert task["pet_id"] == pet_id

    def test_create_owner_level_task_without_pet(self, client):
        task = _create_task(client, name="Buy supplies")
        assert task["pet_id"] is None

    def test_create_task_rejects_unknown_pet(self, client):
        resp = client.post(
            "/api/tasks",
            json={"name": "Walk", "category": "exercise", "pet_id": "nonexistent", "duration": 30},
        )
        assert resp.status_code == 422

    def test_create_task_rejects_negative_duration(self, client):
        resp = client.post("/api/tasks", json={"name": "Walk", "category": "exercise", "duration": -5})
        assert resp.status_code == 422

    def test_get_unknown_task_404(self, client):
        assert client.get("/api/tasks/nonexistent").status_code == 404

    def test_list_tasks_defaults_to_open_only(self, client):
        pet_id = _create_pet(client)
        task = _create_task(client, pet_id=pet_id)
        client.post(f"/api/tasks/{task['task_id']}/complete")

        assert client.get("/api/tasks").json() == []
        assert len(client.get("/api/tasks?status=completed").json()) == 1
        assert len(client.get("/api/tasks?status=all").json()) == 1

    def test_list_tasks_filters_by_pet(self, client):
        pet1 = _create_pet(client, name="Max")
        pet2 = _create_pet(client, name="Whiskers", pet_type="cat", age=2)
        _create_task(client, pet_id=pet1, name="Walk")
        _create_task(client, pet_id=pet2, name="Groom")

        resp = client.get(f"/api/tasks?pet_id={pet1}&status=all")
        assert [t["name"] for t in resp.json()] == ["Walk"]

    def test_list_tasks_sort_by_priority(self, client):
        pet_id = _create_pet(client)
        _create_task(client, pet_id=pet_id, name="Low", priority="low")
        _create_task(client, pet_id=pet_id, name="High", priority="high")

        resp = client.get("/api/tasks?status=all&sort=priority")
        assert [t["name"] for t in resp.json()] == ["High", "Low"]

    def test_patch_task_updates_only_given_fields(self, client):
        pet_id = _create_pet(client)
        task = _create_task(client, pet_id=pet_id, name="Walk", duration=30)
        resp = client.patch(f"/api/tasks/{task['task_id']}", json={"duration": 45})
        assert resp.status_code == 200
        body = resp.json()
        assert body["duration"] == 45
        assert body["name"] == "Walk"

    def test_patch_task_rejects_negative_duration(self, client):
        pet_id = _create_pet(client)
        task = _create_task(client, pet_id=pet_id)
        resp = client.patch(f"/api/tasks/{task['task_id']}", json={"duration": -1})
        assert resp.status_code == 422

    def test_delete_task(self, client):
        pet_id = _create_pet(client)
        task = _create_task(client, pet_id=pet_id)
        resp = client.delete(f"/api/tasks/{task['task_id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/tasks/{task['task_id']}").status_code == 404

    def test_delete_unknown_task_404(self, client):
        assert client.delete("/api/tasks/nonexistent").status_code == 404

    def test_complete_once_task_has_no_next_occurrence(self, client):
        pet_id = _create_pet(client)
        task = _create_task(client, pet_id=pet_id, frequency="once")
        resp = client.post(f"/api/tasks/{task['task_id']}/complete")
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"]["completed"] is True
        assert body["next_occurrence"] is None

    def test_complete_recurring_task_creates_next_occurrence(self, client):
        pet_id = _create_pet(client)
        task = _create_task(client, pet_id=pet_id, name="Feed", frequency="daily")

        resp = client.post(f"/api/tasks/{task['task_id']}/complete")
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"]["completed"] is True
        assert body["next_occurrence"] is not None
        assert body["next_occurrence"]["completed"] is False
        assert body["next_occurrence"]["task_id"] != task["task_id"]

        # the next occurrence is persisted too, not just returned in the response
        all_tasks = client.get("/api/tasks?status=all").json()
        assert len(all_tasks) == 2

    def test_complete_unknown_task_404(self, client):
        assert client.post("/api/tasks/nonexistent/complete").status_code == 404

    def test_uncomplete_task(self, client):
        pet_id = _create_pet(client)
        task = _create_task(client, pet_id=pet_id, frequency="once")
        client.post(f"/api/tasks/{task['task_id']}/complete")

        resp = client.post(f"/api/tasks/{task['task_id']}/uncomplete")
        assert resp.status_code == 200
        assert resp.json()["completed"] is False

    def test_uncomplete_unknown_task_404(self, client):
        assert client.post("/api/tasks/nonexistent/uncomplete").status_code == 404

    def test_overlaps_detected_between_fixed_time_tasks(self, client):
        pet_id = _create_pet(client)
        _create_task(client, pet_id=pet_id, name="Walk", scheduled_time="08:00", duration=30)
        _create_task(client, pet_id=pet_id, name="Feed", scheduled_time="08:15", duration=30)

        resp = client.get("/api/tasks/overlaps")
        assert resp.status_code == 200
        overlaps = resp.json()["overlaps"]
        assert len(overlaps) == 1
        assert "Walk" in overlaps[0] and "Feed" in overlaps[0]

    def test_no_overlaps_when_none_exist(self, client):
        resp = client.get("/api/tasks/overlaps")
        assert resp.status_code == 200
        assert resp.json()["overlaps"] == []


class TestSchedule:
    def test_generate_schedule_returns_tasks_and_conflicts(self, client):
        pet_id = _create_pet(client)
        _create_task(client, pet_id=pet_id, name="Walk", duration=30)

        resp = client.post("/api/schedule/generate")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["schedule"]) == 1
        assert body["schedule"][0]["task"]["name"] == "Walk"
        assert body["conflicts"] == []

    def test_generate_schedule_reports_conflicts(self, client):
        pet_id = _create_pet(client)
        _create_task(client, pet_id=pet_id, name="Walk", scheduled_time="08:00", duration=30)
        _create_task(client, pet_id=pet_id, name="Feed", scheduled_time="08:15", duration=30)

        resp = client.post("/api/schedule/generate")
        assert resp.status_code == 200
        assert len(resp.json()["conflicts"]) == 1
