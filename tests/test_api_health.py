"""FastAPI TestClient tests for the health-records API (documents/extraction,
review, reminders/conflicts, ask, audit).

Each test gets an isolated SQLite file (tmp_path), a fresh VectorStore, and a
MockLLM() injected directly via dependency override -- never touches
data/pawpal.db or a shared process-wide vector store/LLM (see
MIGRATION_PLAN.md §9). PAWPAL_OWNER_KEY is set for every test in this file via
an autouse fixture; the gate itself (unset/wrong/missing key) is covered
separately in test_ai_gate.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.deps import get_health_storage, get_llm_client, get_scheduler_storage, get_vector_store
from api.main import app
from api.services import health_service
from api.storage import SchedulerStorage
from pawpal_ai.llm import MockLLM
from pawpal_ai.storage import init_db as init_health_db
from pawpal_ai.vectorstore import VectorStore

CLEAN_DOC = (
    "Patient: Max\n"
    "Rabies vaccine administered 2025-03-01. Next due 2026-03-01.\n"
    "Amoxicillin 250mg twice a day for 10 days.\n"
    "Follow-up appointment on 2025-04-15.\n"
)

OWNER_KEY = "testkey"


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
    # One VectorStore/MockLLM instance per test, reused across requests --
    # `lambda: VectorStore()` would hand every request a fresh, empty store,
    # so chunks indexed during extraction would never be there for ask().
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


@pytest.fixture(autouse=True)
def owner_key(monkeypatch):
    monkeypatch.setenv("PAWPAL_OWNER_KEY", OWNER_KEY)


def _create_pet(client, name="Max", pet_type="dog", age=3, **extra):
    resp = client.post("/api/pets", json={"name": name, "pet_type": pet_type, "age": age, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["pet_id"]


def _extract(client, pet_id, text=CLEAN_DOC):
    return client.post(
        f"/api/health/pets/{pet_id}/documents:extract",
        data={"text": text},
        headers={"X-PawPal-Owner-Key": OWNER_KEY},
    )


def _document_id_column(health_storage, record_id):
    return health_storage.get_record_document_id(record_id)


class TestExtraction:
    def test_extract_from_pasted_text_creates_pending_records(self, client):
        pet_id = _create_pet(client)
        resp = _extract(client, pet_id)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["document_id"]
        assert len(body["result"]["records"]) >= 1
        assert all(r["review_status"] == "pending" for r in body["result"]["records"])

        # Records are persisted immediately (not held in server-side session
        # state, which a stateless API doesn't have) so the Review step can
        # find them in a later request.
        listed = client.get(f"/api/health/pets/{pet_id}/records").json()
        assert len(listed) == len(body["result"]["records"])

    def test_extract_from_uploaded_file(self, client):
        pet_id = _create_pet(client)
        resp = client.post(
            f"/api/health/pets/{pet_id}/documents:extract",
            files={"file": ("vet_note.txt", CLEAN_DOC.encode("utf-8"), "text/plain")},
            headers={"X-PawPal-Owner-Key": OWNER_KEY},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["doc_type"] == "txt"

    def test_extract_unknown_pet_404(self, client):
        assert _extract(client, "nonexistent-pet").status_code == 404

    def test_extract_rejects_missing_file_and_text(self, client):
        pet_id = _create_pet(client)
        resp = client.post(
            f"/api/health/pets/{pet_id}/documents:extract",
            headers={"X-PawPal-Owner-Key": OWNER_KEY},
        )
        assert resp.status_code == 422

    def test_extract_rejects_too_short_text(self, client):
        pet_id = _create_pet(client)
        assert _extract(client, pet_id, text="hi").status_code == 422


class TestReview:
    def test_reject_record(self, client):
        pet_id = _create_pet(client)
        record_id = _extract(client, pet_id).json()["result"]["records"][0]["record_id"]
        resp = client.post(f"/api/health/records/{record_id}/reject")
        assert resp.status_code == 200
        assert resp.json()["review_status"] == "rejected"

    def test_get_approve_reject_unknown_record_404(self, client):
        assert client.get("/api/health/records/nope").status_code == 404
        assert client.post("/api/health/records/nope/approve").status_code == 404
        assert client.post("/api/health/records/nope/reject").status_code == 404
        assert client.patch("/api/health/records/nope", json={"fields": {}}).status_code == 404

    def test_update_record_merges_fields_without_clobbering_others(self, client):
        pet_id = _create_pet(client)
        records = _extract(client, pet_id).json()["result"]["records"]
        vaccination = next(r for r in records if r["record_type"] == "vaccination")
        original_name = vaccination["fields"].get("vaccine_name")

        resp = client.patch(
            f"/api/health/records/{vaccination['record_id']}",
            json={"fields": {"clinic": "Maple Vet"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["fields"]["clinic"] == "Maple Vet"
        assert body["fields"].get("vaccine_name") == original_name

    def test_approve_and_edit_preserve_document_id(self, client, storages):
        """Regression test for MIGRATION_PLAN.md §7: the old Streamlit page's
        approve/reject always called save_record(rec, document_id=""),
        silently blanking document_id. Approve/reject here call only
        set_review_status, and edit looks the existing id up first."""
        _, health_storage = storages
        pet_id = _create_pet(client)
        extracted = _extract(client, pet_id).json()
        record_id = extracted["result"]["records"][0]["record_id"]
        document_id = extracted["document_id"]
        assert document_id
        assert _document_id_column(health_storage, record_id) == document_id

        client.post(f"/api/health/records/{record_id}/approve")
        assert _document_id_column(health_storage, record_id) == document_id

        client.patch(f"/api/health/records/{record_id}", json={"fields": {"clinic": "Maple Vet"}})
        assert _document_id_column(health_storage, record_id) == document_id

        client.post(f"/api/health/records/{record_id}/reject")
        assert _document_id_column(health_storage, record_id) == document_id


class TestScheduleCare:
    def test_schedule_care_generates_reminder_for_approved_vaccination(self, client):
        pet_id = _create_pet(client)
        records = _extract(client, pet_id).json()["result"]["records"]
        vaccination = next(r for r in records if r["record_type"] == "vaccination")
        client.post(f"/api/health/records/{vaccination['record_id']}/approve")

        resp = client.post(f"/api/health/pets/{pet_id}/schedule-care")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["reminders"]) == 1
        assert body["reminders"][0]["due_date"] == "2026-03-01"

        # Idempotency (MIGRATION_PLAN.md §7): calling it again must not pile
        # up a second reminder row for the same record.
        again = client.post(f"/api/health/pets/{pet_id}/schedule-care")
        assert len(again.json()["reminders"]) == 1
        listed = client.get(f"/api/health/pets/{pet_id}/reminders").json()
        assert len(listed) == 1

    def test_schedule_care_unknown_pet_404(self, client):
        assert client.post("/api/health/pets/nope/schedule-care").status_code == 404


class TestConflicts:
    def test_conflicting_due_dates_block_reminders_until_resolved(self, client):
        pet_id = _create_pet(client)
        doc_a = "Patient: Max\nRabies vaccine administered 2025-03-01. Next due 2026-03-01.\n"
        doc_b = "Patient: Max\nRabies vaccine administered 2025-03-01. Next due 2026-06-15.\n"
        records_a = _extract(client, pet_id, text=doc_a).json()["result"]["records"]
        records_b = _extract(client, pet_id, text=doc_b).json()["result"]["records"]
        for rec in records_a + records_b:
            if rec["record_type"] == "vaccination":
                client.post(f"/api/health/records/{rec['record_id']}/approve")

        resp = client.post(f"/api/health/pets/{pet_id}/schedule-care")
        body = resp.json()
        assert len(body["conflicts"]) == 1
        assert len(body["blocked_record_ids"]) == 2
        assert body["reminders"] == []

        # Idempotency: a second call must not duplicate the conflict row.
        again = client.post(f"/api/health/pets/{pet_id}/schedule-care").json()
        assert len(again["conflicts"]) == 1

        conflict_id = body["conflicts"][0]["conflict_id"]
        resolved = client.post(f"/api/health/conflicts/{conflict_id}/resolve")
        assert resolved.status_code == 200
        assert resolved.json()["resolved"] is True

        unresolved = client.get(
            f"/api/health/pets/{pet_id}/conflicts", params={"unresolved_only": True}
        ).json()
        assert unresolved == []

    def test_resolve_unknown_conflict_404(self, client):
        assert client.post("/api/health/conflicts/nope/resolve").status_code == 404


class TestAsk:
    def test_ask_returns_grounded_answer_with_citations(self, client):
        pet_id = _create_pet(client)
        _extract(client, pet_id)
        resp = client.post(
            f"/api/health/pets/{pet_id}/ask",
            json={"question": "When is the rabies vaccine due?"},
            headers={"X-PawPal-Owner-Key": OWNER_KEY},
        )
        assert resp.status_code == 200
        assert resp.json()["citations"]

    def test_ask_unknown_pet_404(self, client):
        resp = client.post(
            "/api/health/pets/nope/ask",
            json={"question": "hi"},
            headers={"X-PawPal-Owner-Key": OWNER_KEY},
        )
        assert resp.status_code == 404


class TestAudit:
    def test_audit_trail_records_activity(self, client):
        pet_id = _create_pet(client)
        _extract(client, pet_id)
        resp = client.get("/api/health/audit")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


VENDOR_TEXT = (
    "Error code: 401 - {'type': 'error', 'error': {'message': "
    "'invalid x-api-key, fragment: RabiesVaccine2024'}}"
)


class _VendorErrorLLM:
    """Raises what a vendor SDK can: an exception whose text carries provider
    internals and fragments of the request or response."""

    provider = "vendor-error"

    def extract(self, chunks, use_fewshot=True, feedback=""):
        raise RuntimeError(VENDOR_TEXT)

    def answer(self, question, chunks):
        raise RuntimeError(VENDOR_TEXT)


class TestErrorTextNeverReachesClient:
    """UPGRADES.md Priority 2, "raw vendor errors reach the end user", at the
    API boundary. The Streamlit page that item was written against is gone; the
    same leak would now be a JSON response body, which UploadExtractPanel
    renders as "Extraction failed: {fatal_error}"."""

    def test_extraction_failure_returns_a_generic_message(self, client):
        pet_id = _create_pet(client)
        app.dependency_overrides[get_llm_client] = lambda: _VendorErrorLLM()

        resp = _extract(client, pet_id)

        assert resp.status_code == 200, resp.text
        result = resp.json()["result"]
        assert result["records"] == []
        assert result["fatal_error"]
        assert "RabiesVaccine2024" not in resp.text
        assert "x-api-key" not in resp.text

    def test_ask_failure_returns_a_generic_answer(self, client):
        pet_id = _create_pet(client)
        _extract(client, pet_id)  # index real chunks while the working MockLLM is still in place
        app.dependency_overrides[get_llm_client] = lambda: _VendorErrorLLM()

        resp = client.post(
            f"/api/health/pets/{pet_id}/ask",
            json={"question": "When is the rabies vaccine due?"},
            headers={"X-PawPal-Owner-Key": OWNER_KEY},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The failure path specifically, not the low-evidence abstention, which
        # would never have called the LLM at all.
        assert body["abstained"] is True
        assert "couldn't process" in body["answer"]
        assert "RabiesVaccine2024" not in resp.text

    def test_unexpected_value_error_is_not_echoed_as_a_422(self, client, monkeypatch):
        """Only DocumentRejected -- a fixed ingestion message -- is returned
        verbatim. Any other ValueError from inside extraction is a server fault."""
        pet_id = _create_pet(client)

        def _boom(*args, **kwargs):
            raise ValueError(VENDOR_TEXT)

        monkeypatch.setattr(health_service, "process_document", _boom)
        resp = TestClient(app, raise_server_exceptions=False).post(
            f"/api/health/pets/{pet_id}/documents:extract",
            data={"text": CLEAN_DOC},
            headers={"X-PawPal-Owner-Key": OWNER_KEY},
        )

        assert resp.status_code == 500
        assert "RabiesVaccine2024" not in resp.text
