"""Shared FastAPI dependencies: the owner-bound repository, the per-request
language model, and the services.

Per request: api/sessions.py resolves who the request acts for, and
``get_owner_repository`` binds the process-wide storage backend
(api/backend.py) to that owner. Both services are built on that bound
repository, so no handler can reach another owner's data.

**Which AI a request gets** is decided here, from that same context:

- a demo visitor -- no key -- gets :class:`~pawpal_ai.llm.MockLLM`, PawPal's
  free, deterministic, rule-based extractor. Upload, extraction and Ask all
  work for the public on it, and cost nothing;
- the owner space -- reachable only with a valid ``X-PawPal-Owner-Key`` -- gets
  Claude, when the server is configured for it (``PAWPAL_LLM_PROVIDER=claude``
  plus ``ANTHROPIC_API_KEY``), and MockLLM otherwise.

A wrong key never gets this far (api/sessions.py answers 401 before any
handler runs), and there is no other path to the Claude client: paid model
calls are reachable only from the owner space.

Tests override ``get_storage_backend`` / ``get_demo_seeder`` /
``get_llm_client`` via ``app.dependency_overrides`` with isolated instances (a
tmp_path database, no seed, MockLLM()) instead of touching ``data/pawpal.db``
(see MIGRATION_PLAN.md §9).

There is deliberately no vector-store dependency: retrieval chunks are
persisted with the owner's data and HealthService rebuilds the store per
question, so nothing about a document lives only in process memory.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import Depends

from pawpal_ai.config import get_settings
from pawpal_ai.llm import ClaudeLLM, LLMClient, LLMError, MockLLM
from pawpal_ai.logging_setup import log_event

from api.backend import get_demo_seeder, get_storage_backend
from api.repositories.base import OwnerRepository, StorageBackend
from api.services.health_service import HealthService
from api.services.scheduler_service import SchedulerService
from api.sessions import OwnerContext, get_owner_context

__all__ = [
    "PROVIDER_CLAUDE",
    "PROVIDER_MOCK",
    "ai_provider_for",
    "get_claude_llm",
    "get_demo_seeder",
    "get_health_service",
    "get_llm_client",
    "get_mock_llm",
    "get_owner_context",
    "get_owner_repository",
    "get_scheduler_service",
    "get_storage_backend",
]

PROVIDER_MOCK = "mock"
PROVIDER_CLAUDE = "claude"


def get_owner_repository(
    ctx: OwnerContext = Depends(get_owner_context),
    backend: StorageBackend = Depends(get_storage_backend),
) -> OwnerRepository:
    return backend.for_owner(ctx.owner)


@lru_cache
def get_mock_llm() -> LLMClient:
    return MockLLM()


@lru_cache
def get_claude_llm() -> Optional[LLMClient]:
    """The process's Claude client, or None when the server is not configured
    for Claude (provider not "claude", or no API key)."""
    settings = get_settings()
    if not settings.use_claude():
        return None
    try:
        return ClaudeLLM(settings)
    except LLMError:
        log_event("llm_fallback", to="mock", reason="claude_init_failed")
        return None


def ai_provider_for(ctx: OwnerContext) -> str:
    """Which model this context's extraction and Ask run on."""
    return PROVIDER_CLAUDE if ctx.is_owner and get_claude_llm() is not None else PROVIDER_MOCK


def get_llm_client(ctx: OwnerContext = Depends(get_owner_context)) -> LLMClient:
    """FastAPI dependency: the model for this request (see module docstring)."""
    if ctx.is_owner:
        claude = get_claude_llm()
        if claude is not None:
            return claude
    return get_mock_llm()


def get_scheduler_service(repo: OwnerRepository = Depends(get_owner_repository)) -> SchedulerService:
    return SchedulerService(repo)


def get_health_service(
    repo: OwnerRepository = Depends(get_owner_repository),
    llm: LLMClient = Depends(get_llm_client),
) -> HealthService:
    return HealthService(repo, llm)
