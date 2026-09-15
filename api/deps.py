"""Shared FastAPI dependencies: storage singletons + the scheduler/health services.

Storages (and the vector store / LLM client) are kept process-wide (not
created fresh per-request) since this is a single-user app talking to one
SQLite file. Tests override ``get_scheduler_storage``/``get_health_storage``/
``get_vector_store``/``get_llm_client`` via ``app.dependency_overrides`` with
isolated instances (a tmp_path database, a fresh VectorStore, MockLLM())
instead of touching ``data/pawpal.db`` or a shared in-memory store across
tests (see MIGRATION_PLAN.md §9).
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException

from pawpal_ai.config import get_settings
from pawpal_ai.llm import LLMClient, build_llm
from pawpal_ai.storage import Storage as HealthStorage
from pawpal_ai.storage import init_db as init_health_db
from pawpal_ai.vectorstore import VectorStore

from api.services.health_service import HealthService
from api.services.scheduler_service import SchedulerService
from api.storage import SchedulerStorage

_OWNER_KEY_HEADER = "X-PawPal-Owner-Key"


@lru_cache
def get_scheduler_storage() -> SchedulerStorage:
    """Process-wide SchedulerStorage singleton, lazily created on first use."""
    return SchedulerStorage(get_settings().db_path)


@lru_cache
def get_health_storage() -> HealthStorage:
    """Process-wide health-records Storage singleton (pawpal_ai), same db file."""
    return init_health_db(get_settings().db_path)


@lru_cache
def get_vector_store() -> VectorStore:
    """Process-wide VectorStore singleton -- in-memory, lost on restart, same
    as today's per-session Streamlit behavior (see MIGRATION_PLAN.md §5's
    vector-store note; a single-user app needs no per-request isolation)."""
    return VectorStore()


@lru_cache
def get_llm_client() -> LLMClient:
    """Process-wide LLM client, built once from Settings at first use."""
    return build_llm(get_settings())


def get_scheduler_service(
    storage: SchedulerStorage = Depends(get_scheduler_storage),
    health_storage: HealthStorage = Depends(get_health_storage),
) -> SchedulerService:
    def _count_health_records(pet_id: str) -> int:
        return len(health_storage.list_records(pet_id))

    return SchedulerService(storage, health_record_counter=_count_health_records)


def get_health_service(
    health_storage: HealthStorage = Depends(get_health_storage),
    scheduler_storage: SchedulerStorage = Depends(get_scheduler_storage),
    store: VectorStore = Depends(get_vector_store),
    llm: LLMClient = Depends(get_llm_client),
) -> HealthService:
    def _pet_exists(pet_id: str) -> bool:
        # Validate against the one shared pets table (api/storage.py), not
        # pawpal_ai -- which never had a pets table of its own, only a free
        # pet_id string on each record (see MIGRATION_PLAN.md §2's "two
        # disconnected pet lists" fix).
        return scheduler_storage.get_pet(pet_id) is not None

    return HealthService(health_storage, store, llm, pet_exists=_pet_exists)


def require_owner(
    x_pawpal_owner_key: Optional[str] = Header(default=None, alias=_OWNER_KEY_HEADER)
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
