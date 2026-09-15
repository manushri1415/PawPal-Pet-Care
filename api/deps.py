"""Shared FastAPI dependencies: the owner-bound repository and the services.

Per request: api/sessions.py resolves who the request acts for, and
``get_owner_repository`` binds the process-wide storage backend
(api/backend.py) to that owner. Both services are built on that bound
repository, so no handler can reach another owner's data.

Tests override ``get_storage_backend`` / ``get_demo_seeder`` /
``get_vector_store`` / ``get_llm_client`` via ``app.dependency_overrides``
with isolated instances (a tmp_path database, no seed, a fresh VectorStore,
MockLLM()) instead of touching ``data/pawpal.db`` (see MIGRATION_PLAN.md §9).
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException

from pawpal_ai.config import get_settings
from pawpal_ai.llm import LLMClient, build_llm
from pawpal_ai.vectorstore import VectorStore

from api.backend import get_demo_seeder, get_storage_backend
from api.repositories.base import OwnerRepository, StorageBackend
from api.services.health_service import HealthService
from api.services.scheduler_service import SchedulerService
from api.sessions import OWNER_KEY_HEADER, OwnerContext, get_owner_context

__all__ = [
    "get_demo_seeder",
    "get_health_service",
    "get_llm_client",
    "get_owner_context",
    "get_owner_repository",
    "get_scheduler_service",
    "get_storage_backend",
    "get_vector_store",
    "require_owner",
]


def get_owner_repository(
    ctx: OwnerContext = Depends(get_owner_context),
    backend: StorageBackend = Depends(get_storage_backend),
) -> OwnerRepository:
    return backend.for_owner(ctx.owner)


@lru_cache
def get_vector_store() -> VectorStore:
    """Process-wide VectorStore singleton -- in-memory, lost on restart, same
    as today's per-session Streamlit behavior (see MIGRATION_PLAN.md §5's
    vector-store note). Retrieval filters by pet_id, and pet ids are unique
    per owner, so owners do not see each other's chunks."""
    return VectorStore()


@lru_cache
def get_llm_client() -> LLMClient:
    """Process-wide LLM client, built once from Settings at first use."""
    return build_llm(get_settings())


def get_scheduler_service(repo: OwnerRepository = Depends(get_owner_repository)) -> SchedulerService:
    return SchedulerService(repo)


def get_health_service(
    repo: OwnerRepository = Depends(get_owner_repository),
    store: VectorStore = Depends(get_vector_store),
    llm: LLMClient = Depends(get_llm_client),
) -> HealthService:
    return HealthService(repo, store, llm)


def require_owner(
    x_pawpal_owner_key: Optional[str] = Header(default=None, alias=OWNER_KEY_HEADER)
) -> None:
    """AI-gate for the two cost-incurring (LLM-calling) endpoints: extract and
    ask (see MIGRATION_PLAN.md §4). Kept here, not in pawpal_ai/config.py,
    since the gate is an API-layer concern -- reads PAWPAL_OWNER_KEY directly
    rather than adding it to pawpal_ai's Settings.

    Fails closed: an unset key means "AI features not configured", never
    "ungated" -- a forgotten secret must never accidentally open paid
    endpoints to the public. Applied unconditionally on the two routes
    (not gated behind settings.use_claude()) so a flipped provider can't ship
    them open by accident.
    """
    configured = os.getenv("PAWPAL_OWNER_KEY", "").strip()
    if not configured:
        raise HTTPException(
            status_code=503, detail="AI features are not configured on this server."
        )
    if not x_pawpal_owner_key or not secrets.compare_digest(x_pawpal_owner_key, configured):
        raise HTTPException(status_code=401, detail="Missing or invalid owner key.")
