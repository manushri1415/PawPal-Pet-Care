"""SQLite storage backend -- local development, tests, and the Docker image.

One connection, one lock, one file (``data/pawpal.db``) for every table the API
uses. Before this the scheduler tables and the health tables sat behind two
separate connections into the same file (api/storage.py and pawpal_ai's
Storage), which is how two first requests could race each other's
``PRAGMA journal_mode=WAL`` into "database is locked".

Every table carries ``owner_id`` and every statement filters on it, including
lookups by an object's own primary key: ``SELECT ... WHERE owner_id=? AND
record_id=?``. A visitor who learns another visitor's record id still gets
nothing back.

Databases created before owner scoping existed are migrated in place on open:
the health tables gain an ``owner_id`` column defaulting to ``'owner'`` -- the
old single-user owner row's id -- so existing local data becomes the persistent
owner space rather than being lost or exposed to demo visitors.
"""

from __future__ import annotations

import functools
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from pawpal_ai.health_models import Conflict, HealthRecord, Reminder, ReviewStatus
from pawpal_ai.logging_setup import log_event
from pawpal_ai.storage import conflict_id_for
from pawpal_ai.vectorstore import Chunk
from pawpal_system import Pet, Task

from api.repositories.base import (
    KIND_DEMO,
    SNAPSHOT_TABLES,
    ForeignOwnerError,
    OwnerRecord,
    Row,
    default_profile,
    utc_now_iso,
)
from api.repositories.rows import (
    chunk_to_row,
    conflict_to_row,
    pet_to_row,
    record_to_row,
    reminder_to_row,
    row_to_chunk,
    row_to_record,
    row_to_reminder,
    same_conflict,
    strip_owner,
    task_to_row,
)

_F = TypeVar("_F", bound=Callable[..., Any])

# The owner id every pre-session row belongs to (the old singleton owner).
LEGACY_OWNER_ID = "owner"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS owners (
    owner_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'owner',
    expires_at INTEGER,
    name TEXT NOT NULL,
    email TEXT,
    phone_number TEXT,
    available_hours_per_day REAL NOT NULL,
    work_start_hour INTEGER NOT NULL,
    work_start_minute INTEGER NOT NULL,
    work_end_hour INTEGER NOT NULL,
    work_end_minute INTEGER NOT NULL,
    break_between_tasks_minutes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pets (
    pet_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(owner_id),
    name TEXT NOT NULL,
    pet_type TEXT NOT NULL,
    age INTEGER NOT NULL,
    age_months INTEGER NOT NULL DEFAULT 0,
    gender TEXT NOT NULL,
    color TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(owner_id),
    pet_id TEXT REFERENCES pets(pet_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    duration INTEGER NOT NULL,
    priority TEXT NOT NULL,
    frequency TEXT NOT NULL,
    notes TEXT,
    scheduled_time TEXT,
    due_date TEXT NOT NULL,
    end_date TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'owner',
    pet_id TEXT,
    filename TEXT,
    doc_type TEXT,
    char_count INTEGER,
    injection_flagged INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'owner',
    pet_id TEXT,
    record_type TEXT,
    document_id TEXT,
    fields_json TEXT,
    evidence_json TEXT,
    confidence REAL,
    review_status TEXT,
    care_status TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS reminders (
    reminder_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'owner',
    pet_id TEXT,
    record_id TEXT,
    record_type TEXT,
    label TEXT,
    due_date TEXT,
    offsets_json TEXT,
    care_status TEXT,
    source_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS conflicts (
    conflict_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'owner',
    pet_id TEXT,
    record_type TEXT,
    field TEXT,
    value_a TEXT,
    source_a_json TEXT,
    value_b TEXT,
    source_b_json TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'owner',
    event TEXT,
    ref_id TEXT,
    detail TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    owner_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    pet_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    section TEXT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, chunk_id)
);
"""

# Columns added to tables that predate them: (table, column, DDL).
_MIGRATIONS = (
    ("owners", "kind", "TEXT NOT NULL DEFAULT 'owner'"),
    ("owners", "expires_at", "INTEGER"),
    ("documents", "owner_id", "TEXT NOT NULL DEFAULT 'owner'"),
    ("records", "owner_id", "TEXT NOT NULL DEFAULT 'owner'"),
    ("reminders", "owner_id", "TEXT NOT NULL DEFAULT 'owner'"),
    ("conflicts", "owner_id", "TEXT NOT NULL DEFAULT 'owner'"),
    ("audit_log", "owner_id", "TEXT NOT NULL DEFAULT 'owner'"),
)

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_owners_expiry ON owners(kind, expires_at);
CREATE INDEX IF NOT EXISTS idx_pets_owner ON pets(owner_id);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_id);
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id);
CREATE INDEX IF NOT EXISTS idx_records_owner_pet ON records(owner_id, pet_id);
CREATE INDEX IF NOT EXISTS idx_reminders_owner_pet ON reminders(owner_id, pet_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_owner_pet ON conflicts(owner_id, pet_id);
CREATE INDEX IF NOT EXISTS idx_audit_owner ON audit_log(owner_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chunks_owner_pet ON chunks(owner_id, pet_id, created_at, seq);
"""

# Snapshot table -> primary key column.
_PRIMARY_KEYS = {
    "pets": "pet_id",
    "tasks": "task_id",
    "documents": "document_id",
    "records": "record_id",
    "reminders": "reminder_id",
    "conflicts": "conflict_id",
    "audit_log": "id",
    "chunks": "seq",
}

_PROFILE_COLUMNS = tuple(default_profile())


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _locked(method: _F) -> _F:
    """Serialize every use of the backend's single connection.

    The backend is a process-wide singleton and FastAPI runs sync handlers in
    a threadpool, so without this two requests interleave statements and
    commits on one ``sqlite3.Connection``. Reentrant so methods can compose.
    """

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


class SqliteBackend:
    """:class:`~api.repositories.base.StorageBackend` over one SQLite file."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # check_same_thread=False: requests arrive on threadpool threads; the
        # lock above is what makes sharing the connection safe.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.executescript(_INDEXES)
        self._conn.commit()

    def _migrate(self) -> None:
        for table, column, ddl in _MIGRATIONS:
            existing = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    @_locked
    def close(self) -> None:
        self._conn.close()

    # -- owners ---------------------------------------------------------------
    def for_owner(self, owner: OwnerRecord) -> "SqliteOwnerRepository":
        return SqliteOwnerRepository(self, owner)

    @_locked
    def get_owner(self, owner_id: str) -> Optional[OwnerRecord]:
        row = self._conn.execute(
            "SELECT owner_id, kind, expires_at FROM owners WHERE owner_id=?", (owner_id,)
        ).fetchone()
        if row is None:
            return None
        return OwnerRecord(owner_id=row["owner_id"], kind=row["kind"], expires_at=row["expires_at"])

    def _insert_owner(self, owner: OwnerRecord, profile: Row, created_at: Optional[str] = None) -> bool:
        now = utc_now_iso()
        merged = {**default_profile(), **{k: v for k, v in profile.items() if k in _PROFILE_COLUMNS}}
        cols = ("owner_id", "kind", "expires_at", *_PROFILE_COLUMNS, "created_at", "updated_at")
        values = (
            owner.owner_id,
            owner.kind,
            owner.expires_at,
            *(merged[c] for c in _PROFILE_COLUMNS),
            created_at or now,
            now,
        )
        cur = self._conn.execute(
            f"INSERT OR IGNORE INTO owners({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            values,
        )
        return cur.rowcount > 0

    @_locked
    def create_owner(self, owner: OwnerRecord, profile: Optional[Row] = None) -> bool:
        created = self._insert_owner(owner, profile or {})
        self._conn.commit()
        return created

    def _delete_owner_rows(self, owner_id: str) -> None:
        # Children before parents: tasks reference pets, pets reference owners.
        for table in ("tasks", "pets", "documents", "chunks", "records", "reminders", "conflicts", "audit_log"):
            self._conn.execute(f"DELETE FROM {table} WHERE owner_id=?", (owner_id,))
        self._conn.execute("DELETE FROM owners WHERE owner_id=?", (owner_id,))

    @_locked
    def delete_owner(self, owner_id: str) -> None:
        try:
            self._delete_owner_rows(owner_id)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    @_locked
    def purge_expired(self, now_epoch: int, limit: int = 50) -> int:
        """Logical expiry's physical cleanup -- DynamoDB's TTL does this job
        there. Session checks never depend on it having run."""
        rows = self._conn.execute(
            "SELECT owner_id FROM owners WHERE kind=? AND expires_at IS NOT NULL AND expires_at<=?"
            " LIMIT ?",
            (KIND_DEMO, now_epoch, limit),
        ).fetchall()
        try:
            for row in rows:
                self._delete_owner_rows(row["owner_id"])
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return len(rows)

    @_locked
    def import_snapshot(self, owner: OwnerRecord, snapshot: dict[str, Any]) -> None:
        try:
            profile = snapshot.get("profile") or {}
            if not self._insert_owner(owner, profile, created_at=profile.get("created_at")):
                raise ValueError(f"owner {owner.owner_id!r} already exists")
            for table in SNAPSHOT_TABLES:
                for row in snapshot.get(table, []):
                    data = {**row, "owner_id": owner.owner_id}
                    cols = list(data)
                    self._conn.execute(
                        f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        [data[c] for c in cols],
                    )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    @_locked
    def export_snapshot(self, owner_id: str) -> dict[str, Any]:
        profile = self._conn.execute("SELECT * FROM owners WHERE owner_id=?", (owner_id,)).fetchone()
        out: dict[str, Any] = {
            "profile": {k: profile[k] for k in (*_PROFILE_COLUMNS, "created_at")} if profile else None
        }
        for table in SNAPSHOT_TABLES:
            rows = self._conn.execute(
                f"SELECT * FROM {table} WHERE owner_id=? ORDER BY created_at, {_PRIMARY_KEYS[table]}",
                (owner_id,),
            ).fetchall()
            out[table] = [strip_owner(r) for r in rows]
        return out


class SqliteOwnerRepository:
    """:class:`~api.repositories.base.OwnerRepository` for one owner."""

    def __init__(self, backend: SqliteBackend, owner: OwnerRecord):
        self._backend = backend
        self._owner = owner
        self.owner_id = owner.owner_id
        # Shared with the backend: one connection, one lock.
        self._lock = backend._lock
        self._conn = backend._conn

    def _one(self, query: str, params: tuple) -> Optional[Row]:
        row = self._conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def _all(self, query: str, params: tuple) -> list[Row]:
        return [dict(r) for r in self._conn.execute(query, params).fetchall()]

    def _audit(self, event: str, ref_id: str, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO audit_log(id, owner_id, event, ref_id, detail, created_at) VALUES (?,?,?,?,?,?)",
            (_new_id("audit"), self.owner_id, event, ref_id, detail, utc_now_iso()),
        )

    def _upsert(self, table: str, key: str, row: Row) -> None:
        """INSERT, or UPDATE the existing row -- only when it is this owner's.

        The ids are global primary keys, so an upsert keyed on one could in
        principle land on another owner's row. The ``WHERE`` on the conflict
        branch makes that a no-op instead of an overwrite, and the rowcount
        check turns the no-op into an error.
        """
        data = {**row, "owner_id": self.owner_id}
        cols = list(data)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in (key, "owner_id"))
        cur = self._conn.execute(
            f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
            f" ON CONFLICT({key}) DO UPDATE SET {updates} WHERE {table}.owner_id=excluded.owner_id",
            [data[c] for c in cols],
        )
        if cur.rowcount == 0:
            raise ForeignOwnerError(f"{table}.{key} is owned by another owner")

    # -- profile ------------------------------------------------------------
    @_locked
    def get_profile(self) -> Row:
        row = self._one("SELECT * FROM owners WHERE owner_id=?", (self.owner_id,))
        if row is None:
            # The session layer creates the owner before handing out a
            # repository; this only happens when a demo reset or expiry purge
            # removed it mid-request. Recreate it with the same kind and expiry.
            self._backend._insert_owner(self._owner, {})
            self._conn.commit()
            row = self._one("SELECT * FROM owners WHERE owner_id=?", (self.owner_id,))
        return row  # type: ignore[return-value]

    @_locked
    def update_profile(self, **fields: Any) -> Row:
        self.get_profile()
        fields = {k: v for k, v in fields.items() if k in _PROFILE_COLUMNS}
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            self._conn.execute(
                f"UPDATE owners SET {set_clause}, updated_at=? WHERE owner_id=?",
                (*fields.values(), utc_now_iso(), self.owner_id),
            )
            self._conn.commit()
        return self.get_profile()

    # -- pets ---------------------------------------------------------------
    @_locked
    def create_pet(self, pet: Pet) -> Row:
        self.get_profile()  # pets.owner_id references the owner row
        now = utc_now_iso()
        data = {**pet_to_row(pet), "owner_id": self.owner_id, "created_at": now, "updated_at": now}
        cols = list(data)
        self._conn.execute(
            f"INSERT INTO pets({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [data[c] for c in cols],
        )
        self._conn.commit()
        return self.get_pet(pet.id)  # type: ignore[return-value]

    @_locked
    def get_pet(self, pet_id: str) -> Optional[Row]:
        return self._one("SELECT * FROM pets WHERE owner_id=? AND pet_id=?", (self.owner_id, pet_id))

    @_locked
    def list_pets(self) -> list[Row]:
        return self._all("SELECT * FROM pets WHERE owner_id=? ORDER BY created_at", (self.owner_id,))

    @_locked
    def update_pet(self, pet_id: str, **fields: Any) -> Optional[Row]:
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            self._conn.execute(
                f"UPDATE pets SET {set_clause}, updated_at=? WHERE owner_id=? AND pet_id=?",
                (*fields.values(), utc_now_iso(), self.owner_id, pet_id),
            )
            self._conn.commit()
        return self.get_pet(pet_id)

    @_locked
    def delete_pet(self, pet_id: str) -> bool:
        # tasks.pet_id is ON DELETE CASCADE, so the pet's tasks go with it.
        cur = self._conn.execute("DELETE FROM pets WHERE owner_id=? AND pet_id=?", (self.owner_id, pet_id))
        self._conn.commit()
        return cur.rowcount > 0

    # -- tasks --------------------------------------------------------------
    def _insert_task(self, task: Task, now: str) -> None:
        data = {**task_to_row(task), "owner_id": self.owner_id, "created_at": now, "updated_at": now}
        cols = list(data)
        self._conn.execute(
            f"INSERT INTO tasks({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [data[c] for c in cols],
        )

    @_locked
    def create_task(self, task: Task) -> Row:
        self.get_profile()
        self._insert_task(task, utc_now_iso())
        self._conn.commit()
        return self.get_task(task.id)  # type: ignore[return-value]

    @_locked
    def get_task(self, task_id: str) -> Optional[Row]:
        return self._one("SELECT * FROM tasks WHERE owner_id=? AND task_id=?", (self.owner_id, task_id))

    @_locked
    def list_tasks(self, pet_id: Optional[str] = None) -> list[Row]:
        query = "SELECT * FROM tasks WHERE owner_id=?"
        params: list[Any] = [self.owner_id]
        if pet_id is not None:
            query += " AND pet_id=?"
            params.append(pet_id)
        query += " ORDER BY created_at"
        return self._all(query, tuple(params))

    @_locked
    def update_task(self, task_id: str, **fields: Any) -> Optional[Row]:
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            self._conn.execute(
                f"UPDATE tasks SET {set_clause}, updated_at=? WHERE owner_id=? AND task_id=?",
                (*fields.values(), utc_now_iso(), self.owner_id, task_id),
            )
            self._conn.commit()
        return self.get_task(task_id)

    @_locked
    def delete_task(self, task_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM tasks WHERE owner_id=? AND task_id=?", (self.owner_id, task_id))
        self._conn.commit()
        return cur.rowcount > 0

    @_locked
    def complete_task(self, task_id: str, next_task: Optional[Task]) -> bool:
        """One conditional UPDATE and the next occurrence's INSERT, committed
        together. Of concurrent completions only the one whose UPDATE changed a
        row inserts anything."""
        now = utc_now_iso()
        try:
            cur = self._conn.execute(
                "UPDATE tasks SET completed=1, updated_at=?"
                " WHERE owner_id=? AND task_id=? AND completed=0",
                (now, self.owner_id, task_id),
            )
            if cur.rowcount == 0:
                self._conn.rollback()
                return False
            if next_task is not None:
                self._insert_task(next_task, now)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return True

    # -- documents ----------------------------------------------------------
    @_locked
    def save_document(
        self,
        pet_id: str,
        filename: str,
        doc_type: str,
        char_count: int,
        injection_flagged: bool = False,
        document_id: Optional[str] = None,
    ) -> str:
        document_id = document_id or _new_id("doc")
        self._upsert(
            "documents",
            "document_id",
            {
                "document_id": document_id,
                "pet_id": pet_id,
                "filename": filename,
                "doc_type": doc_type,
                "char_count": char_count,
                "injection_flagged": int(injection_flagged),
                "created_at": utc_now_iso(),
            },
        )
        self._audit("document_saved", document_id, doc_type)
        self._conn.commit()
        log_event("record_saved", kind="document", document_id=document_id, chars=char_count)
        return document_id

    # -- chunks ---------------------------------------------------------------
    @_locked
    def save_chunks(self, chunks: list[Chunk]) -> None:
        """Persist a document's retrieval chunks, in order, in one transaction."""
        if not chunks:
            return
        now = utc_now_iso()
        try:
            for seq, chunk in enumerate(chunks):
                data = {**chunk_to_row(chunk, seq), "owner_id": self.owner_id, "created_at": now}
                cols = list(data)
                self._conn.execute(
                    f"INSERT OR REPLACE INTO chunks({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [data[c] for c in cols],
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    @_locked
    def list_chunks(self, pet_id: str, document_id: Optional[str] = None) -> list[Chunk]:
        query = "SELECT * FROM chunks WHERE owner_id=? AND pet_id=?"
        params: list[Any] = [self.owner_id, pet_id]
        if document_id is not None:
            query += " AND document_id=?"
            params.append(document_id)
        query += " ORDER BY created_at, seq"
        return [row_to_chunk(r) for r in self._all(query, tuple(params))]

    # -- records ------------------------------------------------------------
    @_locked
    def save_record(self, record: HealthRecord, document_id: str = "") -> str:
        record.record_id = record.record_id or _new_id("rec")
        self._upsert("records", "record_id", {**record_to_row(record, document_id), "created_at": utc_now_iso()})
        self._audit("record_saved", record.record_id, record.review_status.value)
        self._conn.commit()
        log_event(
            "record_saved",
            kind="record",
            record_id=record.record_id,
            record_type=record.record_type.value,
            review_status=record.review_status.value,
        )
        return record.record_id

    @_locked
    def get_record(self, record_id: str) -> Optional[HealthRecord]:
        row = self._one("SELECT * FROM records WHERE owner_id=? AND record_id=?", (self.owner_id, record_id))
        return row_to_record(row) if row else None

    @_locked
    def get_record_document_id(self, record_id: str) -> Optional[str]:
        row = self._one(
            "SELECT document_id FROM records WHERE owner_id=? AND record_id=?", (self.owner_id, record_id)
        )
        return None if row is None else (row["document_id"] or "")

    @_locked
    def list_records(self, pet_id: str, review_status: Optional[ReviewStatus] = None) -> list[HealthRecord]:
        query = "SELECT * FROM records WHERE owner_id=? AND pet_id=?"
        params: list[Any] = [self.owner_id, pet_id]
        if review_status is not None:
            query += " AND review_status=?"
            params.append(review_status.value)
        query += " ORDER BY created_at"
        return [row_to_record(r) for r in self._all(query, tuple(params))]

    @_locked
    def count_records(self, pet_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM records WHERE owner_id=? AND pet_id=?", (self.owner_id, pet_id)
        ).fetchone()
        return int(row[0])

    @_locked
    def set_review_status(self, record_id: str, status: ReviewStatus) -> None:
        cur = self._conn.execute(
            "UPDATE records SET review_status=? WHERE owner_id=? AND record_id=?",
            (status.value, self.owner_id, record_id),
        )
        if cur.rowcount:
            self._audit(f"record_{status.value}", record_id)
        self._conn.commit()
        log_event("human_review", record_id=record_id, decision=status.value)

    # -- reminders ----------------------------------------------------------
    @_locked
    def save_reminder(self, reminder: Reminder) -> str:
        reminder.reminder_id = reminder.reminder_id or _new_id("rem")
        self._upsert("reminders", "reminder_id", {**reminder_to_row(reminder), "created_at": utc_now_iso()})
        self._audit("reminder_created", reminder.reminder_id, reminder.label)
        self._conn.commit()
        log_event(
            "reminder_created",
            reminder_id=reminder.reminder_id,
            record_id=reminder.record_id,
            due_date=reminder.due_date.isoformat(),
        )
        return reminder.reminder_id

    @_locked
    def list_reminders(self, pet_id: str) -> list[Reminder]:
        rows = self._all(
            "SELECT * FROM reminders WHERE owner_id=? AND pet_id=? ORDER BY due_date", (self.owner_id, pet_id)
        )
        return [row_to_reminder(r) for r in rows]

    # -- conflicts ----------------------------------------------------------
    @_locked
    def save_conflict_if_absent(self, conflict: Conflict) -> Optional[str]:
        # Rows written before conflict ids were deterministic carry random
        # ids, so look for the same conflict by value too, not only by id.
        for row in self._all(
            "SELECT * FROM conflicts WHERE owner_id=? AND pet_id=? AND record_type=? AND field=?",
            (self.owner_id, conflict.pet_id, conflict.record_type.value, conflict.field),
        ):
            if same_conflict(row, conflict):
                return None
        conflict_id = conflict_id_for(conflict)
        data = {**conflict_to_row(conflict, conflict_id), "owner_id": self.owner_id, "created_at": utc_now_iso()}
        cols = list(data)
        cur = self._conn.execute(
            f"INSERT OR IGNORE INTO conflicts({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [data[c] for c in cols],
        )
        if cur.rowcount == 0:
            return None
        self._audit("contradiction_detected", conflict_id, conflict.field)
        self._conn.commit()
        log_event("contradiction_detected", conflict_id=conflict_id, field=conflict.field)
        return conflict_id

    @_locked
    def get_conflict(self, conflict_id: str) -> Optional[Row]:
        return self._one(
            "SELECT * FROM conflicts WHERE owner_id=? AND conflict_id=?", (self.owner_id, conflict_id)
        )

    @_locked
    def list_conflicts(self, pet_id: str, unresolved_only: bool = False) -> list[Row]:
        query = "SELECT * FROM conflicts WHERE owner_id=? AND pet_id=?"
        if unresolved_only:
            query += " AND resolved=0"
        query += " ORDER BY created_at, conflict_id"
        return self._all(query, (self.owner_id, pet_id))

    @_locked
    def resolve_conflict(self, conflict_id: str) -> None:
        cur = self._conn.execute(
            "UPDATE conflicts SET resolved=1 WHERE owner_id=? AND conflict_id=?", (self.owner_id, conflict_id)
        )
        if cur.rowcount:
            self._audit("conflict_resolved", conflict_id)
        self._conn.commit()

    # -- audit --------------------------------------------------------------
    @_locked
    def audit_trail(self, limit: int = 100) -> list[Row]:
        rows = self._all(
            "SELECT id, event, ref_id, detail, created_at FROM audit_log WHERE owner_id=?"
            " ORDER BY created_at DESC, id DESC LIMIT ?",
            (self.owner_id, limit),
        )
        return rows
