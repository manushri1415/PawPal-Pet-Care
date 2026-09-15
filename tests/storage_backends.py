"""Storage backends for tests: SQLite in tmp_path, DynamoDB on moto.

``PAWPAL_TEST_STORAGE=dynamodb`` runs the whole API suite -- sessions,
isolation, scheduler, health, retrieval -- against the DynamoDB backend on an
in-process moto mock, the same way CI runs it. The contract tests in
test_repository_contract.py always run against both.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest import mock

TABLE = "pawpal-test"
_FAKE_AWS = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_REGION": "us-east-1",
}


def selected_storage() -> str:
    return os.getenv("PAWPAL_TEST_STORAGE", "sqlite").strip().lower() or "sqlite"


@contextmanager
def moto_dynamodb() -> Iterator[object]:
    """A moto-mocked DynamoDB with the PawPal table; yields a boto3 client."""
    import boto3
    from moto import mock_aws

    from api.repositories.dynamodb import create_table

    with mock.patch.dict(os.environ, _FAKE_AWS), mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        create_table(client, TABLE)
        yield client


@contextmanager
def storage_backend(kind: str, tmp_path: Path) -> Iterator[object]:
    if kind == "dynamodb":
        from api.repositories.dynamodb import DynamoBackend

        with moto_dynamodb() as client:
            yield DynamoBackend(TABLE, client=client)
        return
    from api.repositories.sqlite import SqliteBackend

    backend = SqliteBackend(tmp_path / "test.db")
    try:
        yield backend
    finally:
        backend.close()


def reopen(kind: str, backend: object, tmp_path: Path) -> object:
    """A brand-new backend object over the same stored data -- what a
    restarted process (or a new Lambda execution environment) would build."""
    if kind == "dynamodb":
        import boto3

        from api.repositories.dynamodb import DynamoBackend

        return DynamoBackend(TABLE, client=boto3.client("dynamodb", region_name="us-east-1"))
    from api.repositories.sqlite import SqliteBackend

    backend.close()
    return SqliteBackend(tmp_path / "test.db")
