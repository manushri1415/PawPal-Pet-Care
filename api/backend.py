"""Process-wide providers: the storage backend and the demo seeder.

Kept apart from api/deps.py so the session layer (api/sessions.py) can depend
on them without an import cycle -- deps.py builds on sessions.py.

``PAWPAL_STORAGE_BACKEND`` picks the backend:

- ``sqlite`` (default) -- one local file at ``PAWPAL_DB_PATH``. Local
  development, the test suite, and the Docker image.
- ``dynamodb`` -- the table named by ``PAWPAL_DYNAMODB_TABLE``, in the region
  the AWS SDK resolves (Lambda sets ``AWS_REGION``). ``PAWPAL_DYNAMODB_ENDPOINT``
  points it at a local DynamoDB instead.

Tests replace these with ``app.dependency_overrides`` (a tmp_path backend; no
seeder, or a specific one) instead of touching real storage.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pawpal_ai.config import get_settings

from api.demo.seed import DemoSeeder, load_default_seeder
from api.repositories.base import StorageBackend
from api.repositories.sqlite import SqliteBackend


def storage_backend_kind() -> str:
    kind = os.getenv("PAWPAL_STORAGE_BACKEND", "sqlite").strip().lower() or "sqlite"
    if kind not in {"sqlite", "dynamodb"}:
        raise RuntimeError(f"PAWPAL_STORAGE_BACKEND must be 'sqlite' or 'dynamodb', not {kind!r}")
    return kind


@lru_cache
def get_storage_backend() -> StorageBackend:
    """The one storage backend for this process, created on first use."""
    if storage_backend_kind() == "dynamodb":
        # Imported only here: boto3 is not needed to run PawPal on SQLite.
        from api.repositories.dynamodb import DynamoBackend

        table = os.getenv("PAWPAL_DYNAMODB_TABLE", "").strip()
        if not table:
            raise RuntimeError("PAWPAL_STORAGE_BACKEND=dynamodb needs PAWPAL_DYNAMODB_TABLE")
        return DynamoBackend(table, endpoint_url=os.getenv("PAWPAL_DYNAMODB_ENDPOINT", "").strip() or None)
    return SqliteBackend(get_settings().db_path)


def get_demo_seeder() -> Optional[DemoSeeder]:
    """The seeded demo dataset new visitor sessions start from, or None to
    start them empty."""
    return load_default_seeder()
