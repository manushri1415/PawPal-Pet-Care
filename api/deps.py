"""Shared FastAPI dependencies: storage singletons + the scheduler service.

Storages are kept process-wide (not created fresh per-request) since this is
a single-user app talking to one SQLite file. Tests override
``get_scheduler_storage``/``get_health_storage`` via
``app.dependency_overrides`` with an isolated tmp_path database instead of
touching ``data/pawpal.db`` (see MIGRATION_PLAN.md §9).

The AI-gate (``require_owner``) for health-records endpoints lands in Phase 3.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from pawpal_ai.config import get_settings
from pawpal_ai.storage import Storage as HealthStorage
from pawpal_ai.storage import init_db as init_health_db

from api.services.scheduler_service import SchedulerService
from api.storage import SchedulerStorage


@lru_cache
def get_scheduler_storage() -> SchedulerStorage:
    """Process-wide SchedulerStorage singleton, lazily created on first use."""
    return SchedulerStorage(get_settings().db_path)


@lru_cache
def get_health_storage() -> HealthStorage:
    """Process-wide health-records Storage singleton (pawpal_ai), same db file.

    Used only so SchedulerService can check for existing health records
    before a pet delete (MIGRATION_PLAN.md §2) -- the scheduler service never
    writes through this handle. The health-records endpoints that own this
    storage land in Phase 3.
    """
    return init_health_db(get_settings().db_path)


def get_scheduler_service(
    storage: SchedulerStorage = Depends(get_scheduler_storage),
    health_storage: HealthStorage = Depends(get_health_storage),
) -> SchedulerService:
    def _count_health_records(pet_id: str) -> int:
        return len(health_storage.list_records(pet_id))

    return SchedulerService(storage, health_record_counter=_count_health_records)
