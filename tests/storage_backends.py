"""Storage backends for tests: SQLite in tmp_path, DynamoDB on moto or DynamoDB Local.

``PAWPAL_TEST_STORAGE=dynamodb`` runs the whole API suite -- sessions,
isolation, scheduler, health, retrieval -- against the DynamoDB backend, the
same way CI runs it. By default that is an in-process moto mock; with
``PAWPAL_TEST_DYNAMODB_ENDPOINT`` (e.g. ``http://localhost:8001`` for the
``amazon/dynamodb-local`` container) it is a real DynamoDB engine, one fresh
table per test. The contract tests in test_repository_contract.py always run
against SQLite and DynamoDB.
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
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


def dynamodb_endpoint() -> Optional[str]:
    """A real DynamoDB endpoint to test against, or None for moto."""
    return os.getenv("PAWPAL_TEST_DYNAMODB_ENDPOINT", "").strip() or None


def dynamodb_is_mocked() -> bool:
    return dynamodb_endpoint() is None


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


def _client(endpoint: Optional[str]):
    import boto3

    return boto3.client("dynamodb", region_name="us-east-1", endpoint_url=endpoint)


@contextmanager
def storage_backend(kind: str, tmp_path: Path) -> Iterator[object]:
    if kind == "dynamodb":
        from api.repositories.dynamodb import DynamoBackend, create_table

        endpoint = dynamodb_endpoint()
        if endpoint is None:
            with moto_dynamodb() as client:
                yield DynamoBackend(TABLE, client=client)
            return
        table = f"pawpal-test-{uuid.uuid4().hex[:12]}"
        with mock.patch.dict(os.environ, _FAKE_AWS):  # DynamoDB Local accepts any credentials
            client = _client(endpoint)
            create_table(client, table)
            try:
                yield DynamoBackend(table, client=client)
            finally:
                client.delete_table(TableName=table)
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
        from api.repositories.dynamodb import DynamoBackend

        return DynamoBackend(backend.table_name, client=_client(dynamodb_endpoint()))
    from api.repositories.sqlite import SqliteBackend

    backend.close()
    return SqliteBackend(tmp_path / "test.db")
