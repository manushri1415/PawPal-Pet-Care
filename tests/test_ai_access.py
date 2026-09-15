"""Who gets which AI.

The public demo must work end to end with no key -- upload, extraction, Ask --
on PawPal's free rule-based MockLLM. Claude, which costs money per call, is
reachable only from the owner space, which only a correct owner key opens. A
wrong key, a missing key, or a server with no key configured must never
produce a single Claude call, whatever else it does.

A recording stand-in replaces the Claude client, so these tests prove which
client each request used without making network calls.
"""

from __future__ import annotations

import pytest

from api import deps
from api.repositories.base import KIND_DEMO, KIND_OWNER, OwnerRecord
from api.sessions import OwnerContext
from pawpal_ai.llm import ClaudeLLM, MockLLM

OWNER_KEY = "owner-key-for-ai-tests"
OWNER = {"X-PawPal-Owner-Key": OWNER_KEY}
DOC = "Patient: Max\nRabies vaccine administered 2025-03-01. Next due 2026-03-01.\n"


class RecordingClaude(MockLLM):
    """Stands in for ClaudeLLM and records every call made to it."""

    provider = "claude"

    def __init__(self):
        self.calls: list[str] = []

    def extract(self, chunks, use_fewshot=True, feedback=""):
        self.calls.append("extract")
        return super().extract(chunks, use_fewshot, feedback)

    def answer(self, question, chunks):
        self.calls.append("answer")
        return super().answer(question, chunks)


@pytest.fixture
def claude(monkeypatch):
    fake = RecordingClaude()
    monkeypatch.setattr(deps, "get_claude_llm", lambda: fake)
    monkeypatch.setenv("PAWPAL_OWNER_KEY", OWNER_KEY)
    return fake


@pytest.fixture
def ai_client(make_client):
    """Clients that go through the real per-request model selection."""

    def factory(**kwargs):
        client = make_client(**kwargs)
        client.app.dependency_overrides.pop(deps.get_llm_client, None)
        return client

    return factory


def _pet(client) -> str:
    resp = client.post("/api/pets", json={"name": "Max", "pet_type": "dog", "age": 3})
    assert resp.status_code == 201, resp.text
    return resp.json()["pet_id"]


def _extract(client, pet_id):
    return client.post(f"/api/health/pets/{pet_id}/documents:extract", data={"text": DOC})


def _ask(client, pet_id):
    return client.post(f"/api/health/pets/{pet_id}/ask", json={"question": "When is the rabies vaccine due?"})


class TestPublicVisitor:
    def test_extracts_and_asks_with_the_free_model_and_no_key(self, ai_client, claude):
        client = ai_client()
        assert client.get("/api/session").json()["ai_provider"] == "mock"
        pet_id = _pet(client)

        extracted = _extract(client, pet_id)
        assert extracted.status_code == 200, extracted.text
        assert extracted.json()["result"]["records"]
        answer = _ask(client, pet_id)
        assert answer.status_code == 200, answer.text
        assert answer.json()["citations"]

        assert claude.calls == []

    def test_upload_works_too(self, ai_client, claude):
        client = ai_client()
        pet_id = _pet(client)
        resp = client.post(
            f"/api/health/pets/{pet_id}/documents:extract",
            files={"file": ("note.txt", DOC.encode(), "text/plain")},
        )
        assert resp.status_code == 200, resp.text
        assert claude.calls == []

    def test_works_when_the_server_has_no_owner_key_at_all(self, ai_client, claude, monkeypatch):
        monkeypatch.delenv("PAWPAL_OWNER_KEY")
        client = ai_client()
        pet_id = _pet(client)
        assert _extract(client, pet_id).status_code == 200
        assert _ask(client, pet_id).status_code == 200
        assert claude.calls == []


class TestOwner:
    def test_a_valid_key_runs_extraction_and_ask_on_claude(self, ai_client, claude):
        owner = ai_client(headers=OWNER)
        assert owner.get("/api/session").json()["ai_provider"] == "claude"
        pet_id = _pet(owner)
        assert _extract(owner, pet_id).status_code == 200
        assert _ask(owner, pet_id).status_code == 200
        assert "extract" in claude.calls and "answer" in claude.calls

    def test_owner_space_without_claude_configured_uses_the_free_model(self, ai_client, monkeypatch):
        monkeypatch.setattr(deps, "get_claude_llm", lambda: None)
        monkeypatch.setenv("PAWPAL_OWNER_KEY", OWNER_KEY)
        owner = ai_client(headers=OWNER)
        assert owner.get("/api/session").json()["ai_provider"] == "mock"
        pet_id = _pet(owner)
        assert _extract(owner, pet_id).status_code == 200


class TestKeysThatMustNeverReachClaude:
    # The last case is a non-ASCII header value, sent as raw bytes (httpx will
    # not encode a str header outside ASCII; a browser or curl will send one).
    @pytest.mark.parametrize("key", ["wrong", OWNER_KEY + "x", OWNER_KEY[:-1], " ", "\xff".encode("latin-1")])
    def test_a_wrong_key_is_refused_before_any_model_call(self, ai_client, claude, key):
        # Build a pet in the owner space first, so a mistaken downgrade would
        # have something to extract into.
        pet_id = _pet(ai_client(headers=OWNER))
        attacker = ai_client(headers={"X-PawPal-Owner-Key": key})
        if key.strip():
            assert _extract(attacker, pet_id).status_code == 401
            assert _ask(attacker, pet_id).status_code == 401
        else:
            # A blank header is no key at all: a demo visitor, who cannot see
            # the owner's pet and gets the free model anyway.
            assert _extract(attacker, pet_id).status_code == 404
        assert claude.calls == []

    def test_no_key_configured_means_no_owner_space_and_no_claude(self, ai_client, claude, monkeypatch):
        monkeypatch.delenv("PAWPAL_OWNER_KEY")
        client = ai_client(headers={"X-PawPal-Owner-Key": "anything"})
        assert client.get("/api/session").status_code == 503
        assert client.post("/api/health/pets/x/ask", json={"question": "hi"}).status_code == 503
        assert claude.calls == []


class TestModelSelection:
    """The selection functions themselves, with the real Claude factory."""

    @pytest.fixture(autouse=True)
    def fresh_clients(self):
        deps.get_claude_llm.cache_clear()
        deps.get_mock_llm.cache_clear()
        yield
        deps.get_claude_llm.cache_clear()
        deps.get_mock_llm.cache_clear()

    @pytest.fixture
    def claude_configured(self, monkeypatch):
        pytest.importorskip("anthropic")
        monkeypatch.setenv("PAWPAL_LLM_PROVIDER", "claude")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")

    def test_claude_needs_both_the_provider_and_an_api_key(self, monkeypatch):
        monkeypatch.setenv("PAWPAL_LLM_PROVIDER", "mock")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
        assert deps.get_claude_llm() is None
        deps.get_claude_llm.cache_clear()
        monkeypatch.setenv("PAWPAL_LLM_PROVIDER", "claude")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        assert deps.get_claude_llm() is None

    def test_a_demo_context_gets_the_free_model_even_when_claude_is_configured(self, claude_configured):
        assert isinstance(deps.get_claude_llm(), ClaudeLLM)
        demo = OwnerContext(OwnerRecord("demo_x", KIND_DEMO, 2_000_000_000), session_token="t")
        owner = OwnerContext(OwnerRecord("owner", KIND_OWNER, None))
        assert isinstance(deps.get_llm_client(demo), MockLLM)
        assert not isinstance(deps.get_llm_client(demo), ClaudeLLM)
        assert isinstance(deps.get_llm_client(owner), ClaudeLLM)
        assert deps.ai_provider_for(demo) == "mock"
        assert deps.ai_provider_for(owner) == "claude"


def test_session_info_carries_no_secrets(ai_client, claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-leave-the-server")
    for client in (ai_client(), ai_client(headers=OWNER)):
        resp = client.get("/api/session")
        assert set(resp.json()) == {"kind", "expires_at", "ai_provider"}
        assert "sk-ant" not in resp.text and OWNER_KEY not in resp.text
