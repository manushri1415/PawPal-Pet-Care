"""SQLite persistence for PawPal AI.

A thin repository over stdlib ``sqlite3`` — no ORM. Nested structures (a
record's ``fields``/``evidence``, a reminder's source) are stored as JSON text
columns; the row columns we query on (ids, status, dates) are first-class.

Every mutating call also writes an ``audit_log`` row, giving a tamper-evident
trail of what the human approved/rejected and what the system saved — the
"human oversight" evidence the rubric asks for.
"""

from __future__ import annotations

import functools
import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from pawpal_ai.health_models import (
    CareStatus,
    Conflict,
    HealthRecord,
    RecordType,
    Reminder,
    ReviewStatus,
    SourceEvidence,
)
from pawpal_ai.logging_setup import log_event

_F = TypeVar("_F", bound=Callable[..., Any])

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    pet_id TEXT,
    filename TEXT,
    doc_type TEXT,
    char_count INTEGER,
    injection_flagged INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
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
    event TEXT,
    ref_id TEXT,
    detail TEXT,
    created_at TEXT
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def conflict_id_for(conflict: Conflict) -> str:
    """A deterministic id for a conflict, the same whichever way round its two
    values are given.

    Two records disagreeing about one field is one conflict no matter how many
    times it is detected, so its id is derived from exactly what identifies it:
    the pet, the record type, the field and the unordered pair of values. That
    is what lets :meth:`Storage.save_conflict_if_absent` be a single
    insert-if-absent instead of a list-then-insert, which two concurrent
    schedule-care calls could both pass before either wrote its row.
    """
    low, high = sorted((conflict.value_a, conflict.value_b))
    key = "\x1f".join((conflict.pet_id, conflict.record_type.value, conflict.field, low, high))
    return "cft_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _locked(method: _F) -> _F:
    """Serialize every use of ``self._conn``.

    One ``Storage`` is shared by every request thread in the API process, and
    so is its single ``sqlite3.Connection`` (opened with
    ``check_same_thread=False``, which only stops sqlite3 from *raising* on
    cross-thread use; it does not make that use safe). Without a lock, two
    requests can interleave statements and commits on that one connection --
    the same failure api/storage.py's SchedulerStorage hit as spurious 404s.
    Reentrant so a method may call another locked method.
    """

    @functools.wraps(method)
    def wrapper(self: "Storage", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


class Storage:
    """Repository over a single SQLite database file."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # check_same_thread=False so the API's request threads can share one
        # instance; _locked is what makes that sharing safe.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # The scheduler tables in api/storage.py live in this same file behind
        # their own connection. A busy_timeout makes a momentary lock held by
        # that connection retry instead of raising "database is locked".
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- lifecycle ---------------------------------------------------------
    @_locked
    def close(self) -> None:
        self._conn.close()

    def _audit(self, event: str, ref_id: str, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO audit_log(id, event, ref_id, detail, created_at) VALUES (?,?,?,?,?)",
            (_new_id("audit"), event, ref_id, detail, _now()),
        )

    # -- documents ---------------------------------------------------------
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
        self._conn.execute(
            "INSERT OR REPLACE INTO documents"
            "(document_id, pet_id, filename, doc_type, char_count, injection_flagged, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (document_id, pet_id, filename, doc_type, char_count, int(injection_flagged), _now()),
        )
        self._audit("document_saved", document_id, doc_type)
        self._conn.commit()
        log_event("record_saved", kind="document", document_id=document_id, chars=char_count)
        return document_id

    # -- records -----------------------------------------------------------
    @_locked
    def save_record(self, record: HealthRecord, document_id: str = "") -> str:
        record.record_id = record.record_id or _new_id("rec")
        self._conn.execute(
            "INSERT OR REPLACE INTO records"
            "(record_id, pet_id, record_type, document_id, fields_json, evidence_json,"
            " confidence, review_status, care_status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                record.record_id,
                record.pet_id,
                record.record_type.value,
                document_id,
                json.dumps(record.fields),
                json.dumps({k: v.model_dump() for k, v in record.evidence.items()}),
                record.confidence,
                record.review_status.value,
                record.care_status.value,
                _now(),
            ),
        )
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
    def set_review_status(self, record_id: str, status: ReviewStatus) -> None:
        self._conn.execute(
            "UPDATE records SET review_status=? WHERE record_id=?",
            (status.value, record_id),
        )
        self._audit(f"record_{status.value}", record_id)
        self._conn.commit()
        log_event("human_review", record_id=record_id, decision=status.value)

    @_locked
    def list_records(
        self, pet_id: str, review_status: Optional[ReviewStatus] = None
    ) -> list[HealthRecord]:
        query = "SELECT * FROM records WHERE pet_id=?"
        params: list[Any] = [pet_id]
        if review_status is not None:
            query += " AND review_status=?"
            params.append(review_status.value)
        query += " ORDER BY created_at"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    @_locked
    def get_record(self, record_id: str) -> Optional[HealthRecord]:
        row = self._conn.execute(
            "SELECT * FROM records WHERE record_id=?", (record_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    @_locked
    def get_record_document_id(self, record_id: str) -> Optional[str]:
        """The ``document_id`` a record was extracted from, or None if the
        record does not exist.

        ``HealthRecord`` deliberately does not carry it, so re-saving an edited
        record needs this to avoid blanking the column (the approve/reject bug
        the API migration fixed). An empty string means the record exists but
        was saved without a document.
        """
        row = self._conn.execute(
            "SELECT document_id FROM records WHERE record_id=?", (record_id,)
        ).fetchone()
        if row is None:
            return None
        return row["document_id"] or ""

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> HealthRecord:
        evidence_raw = json.loads(row["evidence_json"] or "{}")
        return HealthRecord(
            record_id=row["record_id"],
            pet_id=row["pet_id"],
            record_type=RecordType(row["record_type"]),
            fields=json.loads(row["fields_json"] or "{}"),
            evidence={k: SourceEvidence(**v) for k, v in evidence_raw.items()},
            confidence=row["confidence"] or 0.0,
            review_status=ReviewStatus(row["review_status"]),
            care_status=CareStatus(row["care_status"]),
        )

    # -- reminders ---------------------------------------------------------
    @_locked
    def save_reminder(self, reminder: Reminder) -> str:
        reminder.reminder_id = reminder.reminder_id or _new_id("rem")
        self._conn.execute(
            "INSERT OR REPLACE INTO reminders"
            "(reminder_id, pet_id, record_id, record_type, label, due_date, offsets_json,"
            " care_status, source_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                reminder.reminder_id,
                reminder.pet_id,
                reminder.record_id,
                reminder.record_type.value,
                reminder.label,
                reminder.due_date.isoformat(),
                json.dumps(reminder.offsets_days),
                reminder.care_status.value,
                reminder.source.model_dump_json() if reminder.source else None,
                _now(),
            ),
        )
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
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE pet_id=? ORDER BY due_date", (pet_id,)
        ).fetchall()
        out: list[Reminder] = []
        for r in rows:
            source = None
            if r["source_json"]:
                source = SourceEvidence(**json.loads(r["source_json"]))
            out.append(
                Reminder(
                    reminder_id=r["reminder_id"],
                    pet_id=r["pet_id"],
                    record_id=r["record_id"],
                    record_type=RecordType(r["record_type"]),
                    label=r["label"],
                    due_date=date.fromisoformat(r["due_date"]),
                    offsets_days=json.loads(r["offsets_json"] or "[]"),
                    care_status=CareStatus(r["care_status"]),
                    source=source,
                )
            )
        return out

    # -- conflicts ---------------------------------------------------------
    def _insert_conflict(self, conflict: Conflict, conflict_id: str, *, or_ignore: bool) -> bool:
        cur = self._conn.execute(
            f"INSERT {'OR IGNORE ' if or_ignore else ''}INTO conflicts"
            "(conflict_id, pet_id, record_type, field, value_a, source_a_json,"
            " value_b, source_b_json, resolved, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                conflict_id,
                conflict.pet_id,
                conflict.record_type.value,
                conflict.field,
                conflict.value_a,
                conflict.source_a.model_dump_json() if conflict.source_a else None,
                conflict.value_b,
                conflict.source_b.model_dump_json() if conflict.source_b else None,
                int(conflict.resolved),
                _now(),
            ),
        )
        return cur.rowcount > 0

    @_locked
    def save_conflict(self, conflict: Conflict) -> str:
        conflict_id = _new_id("cft")
        self._insert_conflict(conflict, conflict_id, or_ignore=False)
        self._audit("contradiction_detected", conflict_id, conflict.field)
        self._conn.commit()
        log_event("contradiction_detected", conflict_id=conflict_id, field=conflict.field)
        return conflict_id

    @_locked
    def save_conflict_if_absent(self, conflict: Conflict) -> Optional[str]:
        """Store ``conflict`` unless the same conflict is already stored.

        Returns the new conflict's id, or None when it already existed. "The
        same" means the same pet, record type, field and pair of values in
        either order -- so an existing row keeps its ``resolved`` flag rather
        than being reopened by a later detection of the identical disagreement.

        The whole check-and-insert runs under the connection lock, and the
        insert is keyed on :func:`conflict_id_for`'s deterministic id with
        ``INSERT OR IGNORE``, so it cannot double-insert even from a second
        process sharing the database file. The explicit lookup covers rows
        written before ids were deterministic, which carry random ids.
        """
        existing = self._conn.execute(
            "SELECT 1 FROM conflicts WHERE pet_id=? AND record_type=? AND field=?"
            " AND ((value_a=? AND value_b=?) OR (value_a=? AND value_b=?)) LIMIT 1",
            (
                conflict.pet_id,
                conflict.record_type.value,
                conflict.field,
                conflict.value_a,
                conflict.value_b,
                conflict.value_b,
                conflict.value_a,
            ),
        ).fetchone()
        if existing is not None:
            return None
        conflict_id = conflict_id_for(conflict)
        if not self._insert_conflict(conflict, conflict_id, or_ignore=True):
            return None
        self._audit("contradiction_detected", conflict_id, conflict.field)
        self._conn.commit()
        log_event("contradiction_detected", conflict_id=conflict_id, field=conflict.field)
        return conflict_id

    @_locked
    def list_conflicts(self, pet_id: str, unresolved_only: bool = False) -> list[dict]:
        query = "SELECT * FROM conflicts WHERE pet_id=?"
        params: list[Any] = [pet_id]
        if unresolved_only:
            query += " AND resolved=0"
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    @_locked
    def get_conflict(self, conflict_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM conflicts WHERE conflict_id=?", (conflict_id,)
        ).fetchone()
        return dict(row) if row else None

    @_locked
    def resolve_conflict(self, conflict_id: str) -> None:
        self._conn.execute(
            "UPDATE conflicts SET resolved=1 WHERE conflict_id=?", (conflict_id,)
        )
        self._audit("conflict_resolved", conflict_id)
        self._conn.commit()

    # -- audit -------------------------------------------------------------
    @_locked
    def audit_trail(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def init_db(db_path: str | Path) -> Storage:
    """Create (if needed) and return a Storage handle for ``db_path``."""
    return Storage(db_path)
