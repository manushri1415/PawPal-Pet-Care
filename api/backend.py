"""Process-wide providers: the storage backend and the demo seeder.

Kept apart from api/deps.py so the session layer (api/sessions.py) can depend
on them without an import cycle -- deps.py builds on sessions.py.

Tests replace these with ``app.dependency_overrides`` (a tmp_path SQLite
backend; no seeder, or a specific one) instead of touching data/pawpal.db.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pawpal_ai.config import get_settings

from api.demo.seed import DemoSeeder, load_default_seeder
from api.repositories.base import StorageBackend
from api.repositories.sqlite import SqliteBackend


@lru_cache
def get_storage_backend() -> StorageBackend:
    """The one storage backend for this process, created on first use."""
    return SqliteBackend(get_settings().db_path)


def get_demo_seeder() -> Optional[DemoSeeder]:
    """The seeded demo dataset new visitor sessions start from, or None to
    start them empty."""
    return load_default_seeder()
