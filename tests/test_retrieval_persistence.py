"""Ask survives a restart: retrieval chunks are persisted, not process memory.

Before this, the only copy of an uploaded document's text was an in-memory
VectorStore singleton in the API process. Ask worked until the process
restarted and then quietly answered "not enough evidence" about everything --
on Lambda, where every new execution environment is a new process, that is
most of the time.

The contract checked here: extract, Ask, throw away every in-process object
(app, storage backend, LLM client), rebuild them from the same database, Ask
again -- and get the same evidence. And retrieval over the persisted chunks
must rank exactly as the in-memory store did, so the evaluation results the
project reports stay reproducible.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.backend import get_demo_seeder, get_storage_backend
from api.deps import get_llm_client
from api.demo.seed import load_default_seeder
from api.main import create_app
from api.repositories.base import KIND_DEMO, OwnerRecord
from api.repositories.sqlite import SqliteBackend
from api.services.health_service import HealthService
from pawpal_ai import pipeline
from pawpal_ai.documents import ingest_text
from pawpal_ai.llm import MockLLM
from pawpal_ai.pipeline import process_document
from pawpal_ai.qa import answer_question
from pawpal_ai.vectorstore import VectorStore

OWNER_KEY = "persistence-test-key"
HEADERS = {"X-PawPal-Owner-Key": OWNER_KEY}

MAX_DOC = (
    "Happy Paws Veterinary Clinic\n\nPatient: Max\n"
    "Rabies vaccine administered 2025-03-01. Next due 2026-03-01.\n"
    "Distemper (DHPP) vaccine administered 2025-03-01. Next due 2026-03-01.\n\n"
    "Follow-up appointment on 2025-09-01 for annual wellness exam.\n"
)
MAX_MEDS = "Downtown Animal Hospital\nPatient: Max\nAmoxicillin 250mg twice a day for 10 days.\n"
BELLA_DOC = "Patient: Bella\nRabies vaccine administered 2024-01-10. Next due 2027-01-10.\n"

QUESTIONS = [
    "When is the rabies vaccine due?",
    "What medication is Max taking and how often?",
    "When is the follow-up appointment?",
    "What is the capital of France?",  # abstains
    "Should I give Max more amoxicillin?",  # refused
]


@pytest.fixture(autouse=True)
def owner_key(monkeypatch):
    monkeypatch.setenv("PAWPAL_OWNER_KEY", OWNER_KEY)


def _boot(db_path):
    """A complete, fresh API process: new app, new backend, new LLM client."""
    backend = SqliteBackend(db_path)
    app = create_app(dist_dir=db_path.parent / "no-build")
    app.dependency_overrides[get_storage_backend] = lambda: backend
    app.dependency_overrides[get_demo_seeder] = lambda: None
    app.dependency_overrides[get_llm_client] = lambda: MockLLM()
    return backend, TestClient(app, headers=HEADERS)


def _ask(client, pet_id, question):
    resp = client.post(f"/api/health/pets/{pet_id}/ask", json={"question": question})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestAskAfterRestart:
    def test_the_same_evidence_is_available_after_a_restart(self, tmp_path):
        db_path = tmp_path / "pawpal.db"

        backend, client = _boot(db_path)
        pet_id = client.post("/api/pets", json={"name": "Max", "pet_type": "dog", "age": 4}).json()["pet_id"]
        for text in (MAX_DOC, MAX_MEDS):
            assert client.post(f"/api/health/pets/{pet_id}/documents:extract", data={"text": text}).status_code == 200
        before = [_ask(client, pet_id, q) for q in QUESTIONS]
        assert before[0]["citations"] and not before[0]["abstained"]
        client.close()
        backend.close()
        del backend, client

        backend, client = _boot(db_path)
        try:
            after = [_ask(client, pet_id, q) for q in QUESTIONS]
        finally:
            client.close()
            backend.close()

        assert after == before

    def test_a_document_id_filter_still_narrows_to_one_document(self, tmp_path):
        backend, client = _boot(tmp_path / "pawpal.db")
        try:
            pet_id = client.post("/api/pets", json={"name": "Max", "pet_type": "dog", "age": 4}).json()["pet_id"]
            first = client.post(f"/api/health/pets/{pet_id}/documents:extract", data={"text": MAX_DOC}).json()
            client.post(f"/api/health/pets/{pet_id}/documents:extract", data={"text": MAX_MEDS})
            resp = client.post(
                f"/api/health/pets/{pet_id}/ask",
                json={"question": "amoxicillin dosage", "document_id": first["document_id"]},
            ).json()
            assert {c["document_id"] for c in resp["citations"]} <= {first["document_id"]}
        finally:
            client.close()
            backend.close()

    def test_the_seeded_sandbox_can_be_asked_about_without_ever_extracting(self, tmp_path):
        """Seeded documents were never extracted in this process -- their
        chunks come only from storage."""
        seeder = load_default_seeder()
        backend = SqliteBackend(tmp_path / "pawpal.db")
        try:
            owner = OwnerRecord("demo_seeded", KIND_DEMO, None)
            from datetime import date

            seeder.seed(backend, owner, date(2026, 9, 15))
            repo = backend.for_owner(owner)
            max_id = next(p["pet_id"] for p in repo.list_pets() if p["name"] == "Max")
            answer = HealthService(repo, MockLLM()).ask(max_id, "When is the distemper vaccine due?")
            assert not answer.abstained
            assert answer.citations
            assert "2026-10-05" in answer.answer  # 20 days after the seed date
        finally:
            backend.close()


class TestRetrievalIsUnchanged:
    def test_persisted_chunks_rank_exactly_as_the_old_in_memory_store(self, tmp_path, monkeypatch):
        """The old API indexed every document of every pet into one shared
        in-memory store and answered from it. Asking over the chunks rebuilt
        from storage must give identical answers, citations and scores."""
        ids = iter(["doc_max1", "doc_max2", "doc_bella", "doc_max1", "doc_max2", "doc_bella"])
        monkeypatch.setattr(pipeline, "new_document_id", lambda: next(ids))
        llm = MockLLM()

        # Old behaviour: one shared store, documents indexed as extracted.
        shared = VectorStore()
        for text, pet in ((MAX_DOC, "max"), (MAX_MEDS, "max"), (BELLA_DOC, "bella")):
            process_document(ingest_text(text), pet, llm, store=shared)

        # New behaviour: extraction persists chunks, Ask rebuilds from them.
        backend = SqliteBackend(tmp_path / "pawpal.db")
        try:
            owner = OwnerRecord("demo_parity", KIND_DEMO, None)
            backend.create_owner(owner)
            service = HealthService(backend.for_owner(owner), llm)
            for text, pet in ((MAX_DOC, "max"), (MAX_MEDS, "max"), (BELLA_DOC, "bella")):
                service.extract_from_text(pet, text)

            for pet in ("max", "bella"):
                for question in QUESTIONS:
                    old = answer_question(question, shared, llm, pet_id=pet, k=service.settings.retrieval_k)
                    new = service.ask(pet, question)
                    assert new == old, (pet, question)
        finally:
            backend.close()


class TestChunkScoping:
    def test_one_owners_chunks_are_invisible_to_another(self, backend):
        alice = OwnerRecord("demo_alice", KIND_DEMO, None)
        bob = OwnerRecord("demo_bob", KIND_DEMO, None)
        for owner in (alice, bob):
            backend.create_owner(owner)
        HealthService(backend.for_owner(alice), MockLLM()).extract_from_text("shared-pet-id", MAX_DOC)

        assert backend.for_owner(alice).list_chunks("shared-pet-id")
        assert backend.for_owner(bob).list_chunks("shared-pet-id") == []
        answer = HealthService(backend.for_owner(bob), MockLLM()).ask("shared-pet-id", "When is rabies due?")
        assert answer.abstained and answer.citations == []

    def test_chunks_are_listed_in_saved_order_and_scoped_to_the_pet(self, backend):
        owner = OwnerRecord("demo_order", KIND_DEMO, None)
        backend.create_owner(owner)
        repo = backend.for_owner(owner)
        service = HealthService(repo, MockLLM())
        first = service.extract_from_text("max", MAX_DOC).document_id
        second = service.extract_from_text("max", MAX_MEDS).document_id
        service.extract_from_text("bella", BELLA_DOC)

        chunks = repo.list_chunks("max")
        assert [c.document_id for c in chunks] == sorted(
            [c.document_id for c in chunks], key=[first, second].index
        )
        assert {c.pet_id for c in chunks} == {"max"}
        assert repo.list_chunks("max", document_id=second) == [c for c in chunks if c.document_id == second]

    def test_a_demo_reset_removes_the_chunks(self, backend):
        owner = OwnerRecord("demo_reset", KIND_DEMO, None)
        backend.create_owner(owner)
        HealthService(backend.for_owner(owner), MockLLM()).extract_from_text("max", MAX_DOC)
        backend.delete_owner(owner.owner_id)
        backend.create_owner(owner)
        assert backend.for_owner(owner).list_chunks("max") == []


def test_there_is_no_process_wide_vector_store_left():
    import api.deps

    assert not hasattr(api.deps, "get_vector_store")
