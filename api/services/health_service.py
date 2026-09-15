"""Domain glue for the health-records API: extraction, review, reminders,
conflicts, ask, and audit -- all sitting on top of the existing pawpal_ai
pipeline/storage without changing either (see MIGRATION_PLAN.md §7: "Nothing
else in pawpal_system.py/pawpal_ai/ changes").

This is also where the Streamlit-era bugs get fixed for good, per §7:

- **Extraction now persists records immediately** (PENDING, with the correct
  ``document_id``) instead of only living in ``st.session_state.pending`` --
  a stateless API has no server-side session to hold them in between the
  Upload and Review steps.
- **Approve/reject call only ``set_review_status``** (a targeted column
  update), never ``save_record`` -- the old page's
  ``save_record(rec, document_id="")`` silently blanked ``document_id`` on
  every approve/reject.
- **Editing a record's fields preserves its ``document_id``.** ``HealthRecord``
  (and ``Storage.get_record``) don't carry ``document_id`` -- only the
  underlying `records` table column does -- so ``_document_id_for_record``
  below reads it directly off ``Storage``'s own connection rather than adding
  a new pawpal_ai method for this one call site.
- **``schedule-care`` calls ``approve_and_schedule`` directly** (the
  combinator the old page never actually used) and is idempotent: reminders
  upsert under a deterministic ``rem_<record_id>`` id, and conflicts are
  deduped by ``(record_type, field, value_a, value_b)`` (either order)
  against what's already stored, so calling it repeatedly never piles up
  duplicate rows.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Callable, Optional

from pawpal_ai.config import Settings, get_settings
from pawpal_ai.documents import DocumentResult, ingest_bytes, ingest_text
from pawpal_ai.health_models import HealthRecord, QAAnswer, Reminder, ReviewStatus
from pawpal_ai.llm import LLMClient
from pawpal_ai.pipeline import approve_and_schedule, process_document
from pawpal_ai.qa import answer_question
from pawpal_ai.storage import Storage as HealthStorage
from pawpal_ai.vectorstore import VectorStore

from api.schemas.health import (
    AuditEntryRead,
    ConflictRead,
    DocumentExtractResponse,
    RecordUpdate,
    ScheduleCareResponse,
)


def _raw_row(storage: HealthStorage, query: str, params: tuple) -> Optional[sqlite3.Row]:
    """Direct read against Storage's own SQLite connection, for the couple of
    lookups pawpal_ai.Storage doesn't expose a method for (a record's
    ``document_id``; a conflict by id with no pet_id in hand). Read-only,
    against the same ``records``/``conflicts`` tables Storage already owns --
    chosen over adding a new pawpal_ai method for a single API-layer need."""
    return storage._conn.execute(query, params).fetchone()


class HealthService:
    def __init__(
        self,
        storage: HealthStorage,
        store: VectorStore,
        llm: LLMClient,
        settings: Optional[Settings] = None,
        pet_exists: Optional[Callable[[str], bool]] = None,
    ):
        self.storage = storage
        self.store = store
        self.llm = llm
        self.settings = settings or get_settings()
        self._pet_exists = pet_exists or (lambda pet_id: True)

    def pet_exists(self, pet_id: str) -> bool:
        return self._pet_exists(pet_id)

    # -- documents / extraction ---------------------------------------------

    def extract_from_upload(self, pet_id: str, data: bytes, filename: str) -> DocumentExtractResponse:
        return self._extract(pet_id, ingest_bytes(data, filename))

    def extract_from_text(self, pet_id: str, text: str) -> DocumentExtractResponse:
        return self._extract(pet_id, ingest_text(text))

    def _extract(self, pet_id: str, doc: DocumentResult) -> DocumentExtractResponse:
        if not doc.ok:
            raise ValueError(doc.error or "Could not read the document.")

        processed = process_document(doc, pet_id, self.llm, self.settings, store=self.store)
        document_id = self.storage.save_document(
            pet_id, doc.filename, doc.doc_type, doc.char_count, doc.injection_flagged, processed.document_id
        )
        for rec in processed.result.records:
            self.storage.save_record(rec, document_id=document_id)

        return DocumentExtractResponse(
            document_id=document_id,
            filename=doc.filename,
            doc_type=doc.doc_type,
            char_count=doc.char_count,
            injection_flagged=doc.injection_flagged,
            result=processed.result,
        )

    # -- records / review -----------------------------------------------------

    def list_records(self, pet_id: str, review_status: Optional[ReviewStatus] = None) -> list[HealthRecord]:
        return self.storage.list_records(pet_id, review_status)

    def get_record(self, record_id: str) -> Optional[HealthRecord]:
        return self.storage.get_record(record_id)

    def approve_record(self, record_id: str) -> Optional[HealthRecord]:
        if self.storage.get_record(record_id) is None:
            return None
        self.storage.set_review_status(record_id, ReviewStatus.APPROVED)
        return self.storage.get_record(record_id)

    def reject_record(self, record_id: str) -> Optional[HealthRecord]:
        if self.storage.get_record(record_id) is None:
            return None
        self.storage.set_review_status(record_id, ReviewStatus.REJECTED)
        return self.storage.get_record(record_id)

    def update_record(self, record_id: str, patch: RecordUpdate) -> Optional[HealthRecord]:
        current = self.storage.get_record(record_id)
        if current is None:
            return None
        current.fields.update(patch.fields)
        self.storage.save_record(current, document_id=self._document_id_for_record(record_id))
        return self.storage.get_record(record_id)

    def _document_id_for_record(self, record_id: str) -> str:
        row = _raw_row(self.storage, "SELECT document_id FROM records WHERE record_id=?", (record_id,))
        return (row["document_id"] if row else None) or ""

    # -- schedule-care / reminders / conflicts ---------------------------------

    def schedule_care(self, pet_id: str) -> ScheduleCareResponse:
        approved = self.storage.list_records(pet_id, ReviewStatus.APPROVED)
        reminders, conflicts, blocked = approve_and_schedule(approved, settings=self.settings)

        for reminder in reminders:
            # Deterministic id -> INSERT OR REPLACE upserts instead of a fresh
            # row every call (MIGRATION_PLAN.md §7's "reminders duplicate
            # forever" fix).
            reminder.reminder_id = f"rem_{reminder.record_id}"
            self.storage.save_reminder(reminder)

        existing_keys = set()
        for row in self.storage.list_conflicts(pet_id):
            key = (row["record_type"], row["field"], row["value_a"], row["value_b"])
            existing_keys.add(key)
            existing_keys.add((key[0], key[1], key[3], key[2]))  # either order
        for conflict in conflicts:
            key = (conflict.record_type.value, conflict.field, conflict.value_a, conflict.value_b)
            if key in existing_keys:
                continue
            self.storage.save_conflict(conflict)
            existing_keys.add(key)

        return ScheduleCareResponse(
            reminders=self.storage.list_reminders(pet_id),
            conflicts=[self._conflict_row_to_schema(r) for r in self.storage.list_conflicts(pet_id)],
            blocked_record_ids=sorted(blocked),
        )

    def list_reminders(self, pet_id: str) -> list[Reminder]:
        return self.storage.list_reminders(pet_id)

    def list_conflicts(self, pet_id: str, unresolved_only: bool = False) -> list[ConflictRead]:
        return [
            self._conflict_row_to_schema(r)
            for r in self.storage.list_conflicts(pet_id, unresolved_only)
        ]

    def resolve_conflict(self, conflict_id: str) -> Optional[ConflictRead]:
        row = _raw_row(self.storage, "SELECT * FROM conflicts WHERE conflict_id=?", (conflict_id,))
        if row is None:
            return None
        self.storage.resolve_conflict(conflict_id)
        row = _raw_row(self.storage, "SELECT * FROM conflicts WHERE conflict_id=?", (conflict_id,))
        return self._conflict_row_to_schema(row)

    @staticmethod
    def _conflict_row_to_schema(row) -> ConflictRead:
        return ConflictRead(
            conflict_id=row["conflict_id"],
            pet_id=row["pet_id"],
            record_type=row["record_type"],
            field=row["field"],
            value_a=row["value_a"],
            source_a=json.loads(row["source_a_json"]) if row["source_a_json"] else None,
            value_b=row["value_b"],
            source_b=json.loads(row["source_b_json"]) if row["source_b_json"] else None,
            resolved=bool(row["resolved"]),
        )

    # -- ask --------------------------------------------------------------------

    def ask(self, pet_id: str, question: str, document_id: Optional[str] = None) -> QAAnswer:
        return answer_question(
            question, self.store, self.llm, pet_id=pet_id, k=self.settings.retrieval_k, document_id=document_id
        )

    # -- audit ------------------------------------------------------------------

    def audit_trail(self, limit: int = 100) -> list[AuditEntryRead]:
        return [AuditEntryRead(**row) for row in self.storage.audit_trail(limit)]
