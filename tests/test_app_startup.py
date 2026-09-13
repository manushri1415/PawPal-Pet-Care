"""The startup warning for a database that does not exist yet (api/main.py).

It exists so a deployment can't silently lose its data -- most commonly a
`docker run` without a volume, which boots every new container onto an empty
database. The lifespan test is the one that carries the weight: the check only
means anything if it runs *before* the storages are constructed, because
building either one creates the file.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from api import main
from api.deps import get_health_storage, get_scheduler_storage

WARNING_TEXT = "starting with a new, empty database"


def _new_database_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if WARNING_TEXT in r.getMessage()]


def _reset_storage_singletons() -> None:
    for getter in (get_scheduler_storage, get_health_storage):
        if getter.cache_info().currsize:
            getter().close()
        getter.cache_clear()


class TestWarnIfDatabaseIsNew:
    def test_warns_when_the_file_is_missing(self, tmp_path, caplog):
        with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
            main._warn_if_database_is_new(tmp_path / "pawpal.db")
        assert _new_database_warnings(caplog)

    def test_silent_when_the_file_exists(self, tmp_path, caplog):
        db_path = tmp_path / "pawpal.db"
        db_path.touch()
        with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
            main._warn_if_database_is_new(db_path)
        assert not _new_database_warnings(caplog)


class TestLifespan:
    """Drives the real lifespan -- the real storage singletons, pointed at a
    tmp_path database -- rather than the helper alone."""

    @pytest.fixture
    def db_path(self, tmp_path, monkeypatch):
        db_path = tmp_path / "pawpal.db"
        monkeypatch.setenv("PAWPAL_DB_PATH", str(db_path))
        _reset_storage_singletons()
        yield db_path
        _reset_storage_singletons()

    @staticmethod
    def _boot(tmp_path) -> None:
        # A dist_dir with no build in it keeps the app in API-only mode.
        with TestClient(main.create_app(dist_dir=tmp_path / "no-build")) as client:
            assert client.get("/api/healthz").status_code == 200

    def test_first_boot_warns_and_a_reboot_onto_existing_data_does_not(self, db_path, tmp_path, caplog):
        with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
            self._boot(tmp_path)
        assert _new_database_warnings(caplog), "a first boot with no database must warn"
        assert db_path.exists()

        caplog.clear()
        _reset_storage_singletons()  # a fresh process, as a redeployed container would be
        with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
            self._boot(tmp_path)
        assert not _new_database_warnings(caplog), "a boot onto existing data must stay quiet"
