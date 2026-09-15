"""Tests for the owner-key AI-gate (MIGRATION_PLAN.md §4): the two LLM-calling
endpoints (documents:extract, ask) require ``X-PawPal-Owner-Key`` to match
``PAWPAL_OWNER_KEY``.

- No key configured on the server -> 503 (fail closed; never "ungated").
- Missing/wrong header -> 401.
- Correct header -> 200.

Every other health-records endpoint is free and must work with no key
configured at all. Runs with MockLLM (free, deterministic) via dependency
override, same as test_api_health.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.deps import get_health_storage, get_llm_client, get_scheduler_storage, get_vector_store
from api.main import app
from api.storage import SchedulerStorage
from pawpal_ai.llm import MockLLM
from pawpal_ai.storage import init_db as init_health_db
from pawpal_ai.vectorstore import VectorStore

SOME_TEXT = "Rabies vaccine administered 2025-03-01. Next due 2026-03-01."


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
    # One instance per test, reused across requests (see test_api_health.py).
    vector_store = VectorStore()
    llm = MockLLM()
    app.dependency_overrides[get_scheduler_storage] = lambda: scheduler_storage
    app.dependency_overrides[get_health_storage] = lambda: health_storage
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_llm_client] = lambda: llm
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_pet(client):
    resp = client.post("/api/pets", json={"name": "Max", "pet_type": "dog", "age": 3})
    assert resp.status_code == 201, resp.text
    return resp.json()["pet_id"]


class TestExtractGate:
    def test_no_key_configured_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("PAWPAL_OWNER_KEY", raising=False)
        resp = client.post(
            "/api/health/pets/anything/documents:extract",
            data={"text": SOME_TEXT},
            headers={"X-PawPal-Owner-Key": "whatever"},
        )
        assert resp.status_code == 503

    def test_missing_header_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("PAWPAL_OWNER_KEY", "secret123")
        resp = client.post("/api/health/pets/anything/documents:extract", data={"text": SOME_TEXT})
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("PAWPAL_OWNER_KEY", "secret123")
        resp = client.post(
            "/api/health/pets/anything/documents:extract",
            data={"text": SOME_TEXT},
            headers={"X-PawPal-Owner-Key": "wrong"},
        )
        assert resp.status_code == 401

    def test_correct_key_passes_gate(self, client, monkeypatch):
        monkeypatch.setenv("PAWPAL_OWNER_KEY", "secret123")
        pet_id = _create_pet(client)
        resp = client.post(
            f"/api/health/pets/{pet_id}/documents:extract",
            data={"text": SOME_TEXT},
            headers={"X-PawPal-Owner-Key": "secret123"},
        )
        assert resp.status_code == 200


class TestAskGate:
    def test_no_key_configured_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("PAWPAL_OWNER_KEY", raising=False)
        resp = client.post("/api/health/pets/anything/ask", json={"question": "hi"})
        assert resp.status_code == 503

    def test_missing_header_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("PAWPAL_OWNER_KEY", "secret123")
        resp = client.post("/api/health/pets/anything/ask", json={"question": "hi"})
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("PAWPAL_OWNER_KEY", "secret123")
        resp = client.post(
            "/api/health/pets/anything/ask",
            json={"question": "hi"},
            headers={"X-PawPal-Owner-Key": "wrong"},
        )
        assert resp.status_code == 401

    def test_correct_key_passes_gate(self, client, monkeypatch):
        monkeypatch.setenv("PAWPAL_OWNER_KEY", "secret123")
        pet_id = _create_pet(client)
        resp = client.post(
            f"/api/health/pets/{pet_id}/ask",
            json={"question": "hi"},
            headers={"X-PawPal-Owner-Key": "secret123"},
        )
        assert resp.status_code == 200


class TestFreeEndpointsAreUngated:
    def test_records_list_works_with_no_key_configured(self, client, monkeypatch):
        monkeypatch.delenv("PAWPAL_OWNER_KEY", raising=False)
        pet_id = _create_pet(client)
        assert client.get(f"/api/health/pets/{pet_id}/records").status_code == 200

    def test_reminders_and_audit_work_with_no_key_configured(self, client, monkeypatch):
        monkeypatch.delenv("PAWPAL_OWNER_KEY", raising=False)
        pet_id = _create_pet(client)
        assert client.get(f"/api/health/pets/{pet_id}/reminders").status_code == 200
        assert client.get("/api/health/audit").status_code == 200
