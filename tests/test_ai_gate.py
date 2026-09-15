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

SOME_TEXT = "Rabies vaccine administered 2025-03-01. Next due 2026-03-01."


@pytest.fixture
def client(make_client):
    return make_client()


def _create_pet(client, headers=None):
    resp = client.post("/api/pets", json={"name": "Max", "pet_type": "dog", "age": 3}, headers=headers)
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
        pet_id = _create_pet(client, headers={"X-PawPal-Owner-Key": "secret123"})
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
        pet_id = _create_pet(client, headers={"X-PawPal-Owner-Key": "secret123"})
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
