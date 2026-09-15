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
  (and ``get_record``) don't carry ``document_id`` -- only the
  underlying `records` table column does -- so the edit looks it up first
  with ``get_record_document_id``.
- **``schedule-care`` calls ``approve_and_schedule`` directly** (the
  combinator the old page never actually used) and is idempotent: reminders
  upsert under a deterministic ``rem_<record_id>`` id, and each conflict is
  stored with ``save_conflict_if_absent`` -- deduped by
  ``(record_type, field, value_a, value_b)`` in either order, as one
  insert-if-absent rather than a list-then-insert that two concurrent calls
  could both pass -- so calling it repeatedly never piles up duplicate rows.
- **Ask keeps working across restarts.** Extraction persists each document's
  retrieval chunks alongside its records; Ask loads the pet's chunks and
  rebuilds the same deterministic ``VectorStore`` from them for the question.
  The store used to be a process-wide in-memory singleton and the only copy of
  that text -- every restart (and on Lambda, every new execution environment)
  silently forgot every document ever uploaded.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional

from pawpal_ai.config import Settings, get_settings
from pawpal_ai.documents import DocumentResult, ingest_bytes, ingest_text
from pawpal_ai.health_models import HealthRecord, QAAnswer, Reminder, ReviewStatus
from pawpal_ai.llm import LLMClient
from pawpal_ai.pipeline import approve_and_schedule, process_document
from pawpal_ai.qa import answer_question
from pawpal_ai.vectorstore import VectorStore

from api.repositories.base import OwnerRepository
from api.schemas.health import (
    AuditEntryRead,
    ConflictRead,
    DocumentExtractResponse,
    RecordUpdate,
    ScheduleCareResponse,
)


class DocumentRejected(ValueError):
    """The upload or pasted text could not be ingested at all.

    Its message is one of pawpal_ai.documents' fixed, user-facing strings
    ("Unsupported file type ...", "Could not read the ... file"), so the router
    returns it to the client verbatim. That is the whole reason this is its own
    type: the router used to catch *any* ValueError around extraction and echo
    ``str(e)`` as the 422 detail, and a ValueError raised from deeper in the
    pipeline -- pydantic's ValidationError is one -- can carry arbitrary
    internal or model-derived text (UPGRADES.md Priority 2).
    """


class HealthService:
    def __init__(
        self,
        repo: OwnerRepository,
        llm: LLMClient,
        settings: Optional[Settings] = None,
    ):
        # Bound to this request's owner (api/repositories/base.py): every
        # record, reminder, conflict, chunk and audit entry below is that owner's.
        self.repo = repo
        self.llm = llm
        self.settings = settings or get_settings()

    def pet_exists(self, pet_id: str) -> bool:
        # The one shared pets table, scoped to this owner -- another owner's
        # pet id is "not found" here, same as a made-up one.
        return self.repo.get_pet(pet_id) is not None

    # -- documents / extraction ---------------------------------------------

    def extract_from_upload(self, pet_id: str, data: bytes, filename: str) -> DocumentExtractResponse:
        return self._extract(pet_id, ingest_bytes(data, filename))

    def extract_from_text(self, pet_id: str, text: str) -> DocumentExtractResponse:
        return self._extract(pet_id, ingest_text(text))

    def _extract(self, pet_id: str, doc: DocumentResult) -> DocumentExtractResponse:
        if not doc.ok:
            raise DocumentRejected(doc.error or "Could not read the document.")

        # A store of this document's own chunks: extraction only ever retrieves
        # within the document it is extracting (document_id-filtered), so a
        # store holding other documents would change nothing but its size.
        store = VectorStore()
        processed = process_document(doc, pet_id, self.llm, self.settings, store=store)
        document_id = self.repo.save_document(
            pet_id, doc.filename, doc.doc_type, doc.char_count, doc.injection_flagged, processed.document_id
        )
        # The chunks are the one durable copy of the document's text -- the
        # uploaded bytes themselves are never stored -- and what Ask retrieves
        # from later. Saved before the records whose evidence cites them.
        self.repo.save_chunks(store.all_chunks(processed.document_id))
        for rec in processed.result.records:
            self.repo.save_record(rec, document_id=document_id)

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
        return self.repo.list_records(pet_id, review_status)

    def get_record(self, record_id: str) -> Optional[HealthRecord]:
        return self.repo.get_record(record_id)

    def approve_record(self, record_id: str) -> Optional[HealthRecord]:
        if self.repo.get_record(record_id) is None:
            return None
        self.repo.set_review_status(record_id, ReviewStatus.APPROVED)
        return self.repo.get_record(record_id)

    def reject_record(self, record_id: str) -> Optional[HealthRecord]:
        if self.repo.get_record(record_id) is None:
            return None
        self.repo.set_review_status(record_id, ReviewStatus.REJECTED)
        return self.repo.get_record(record_id)

    def update_record(self, record_id: str, patch: RecordUpdate) -> Optional[HealthRecord]:
        current = self.repo.get_record(record_id)
        if current is None:
            return None
        current.fields.update(patch.fields)
        document_id = self.repo.get_record_document_id(record_id) or ""
        self.repo.save_record(current, document_id=document_id)
        return self.repo.get_record(record_id)

    # -- schedule-care / reminders / conflicts ---------------------------------

    def schedule_care(self, pet_id: str, today: Optional[date] = None) -> ScheduleCareResponse:
        """``today`` is the visitor's local date (api/clock.py) -- it decides
        whether a reminder reads overdue, due soon or current, so the server's
        UTC date would mislabel one near midnight."""
        approved = self.repo.list_records(pet_id, ReviewStatus.APPROVED)
        reminders, conflicts, blocked = approve_and_schedule(
            approved, today=today, settings=self.settings
        )

        for reminder in reminders:
            # Deterministic id -> INSERT OR REPLACE upserts instead of a fresh
            # row every call (MIGRATION_PLAN.md §7's "reminders duplicate
            # forever" fix).
            reminder.reminder_id = f"rem_{reminder.record_id}"
            self.repo.save_reminder(reminder)

        for conflict in conflicts:
            self.repo.save_conflict_if_absent(conflict)

        return ScheduleCareResponse(
            reminders=self.repo.list_reminders(pet_id),
            conflicts=[self._conflict_row_to_schema(r) for r in self.repo.list_conflicts(pet_id)],
            blocked_record_ids=sorted(blocked),
        )

    def list_reminders(self, pet_id: str) -> list[Reminder]:
        return self.repo.list_reminders(pet_id)

    def list_conflicts(self, pet_id: str, unresolved_only: bool = False) -> list[ConflictRead]:
        return [
            self._conflict_row_to_schema(r)
            for r in self.repo.list_conflicts(pet_id, unresolved_only)
        ]

    def resolve_conflict(self, conflict_id: str) -> Optional[ConflictRead]:
        if self.repo.get_conflict(conflict_id) is None:
            return None
        self.repo.resolve_conflict(conflict_id)
        return self._conflict_row_to_schema(self.repo.get_conflict(conflict_id))

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
        # Rebuilt per question from persisted chunks: the embeddings are a
        # deterministic hash of the text, so this store ranks exactly as the
        # one the chunks were first indexed into -- for this pet, in the same
        # order -- and retrieval behaves exactly as answer_question expects.
        # A pet's documents are a handful of short chunks, so embedding them
        # per request costs well under a millisecond each.
        store = VectorStore()
        store.add(self.repo.list_chunks(pet_id))
        return answer_question(
            question, store, self.llm, pet_id=pet_id, k=self.settings.retrieval_k, document_id=document_id
        )

    # -- audit ------------------------------------------------------------------

    def audit_trail(self, limit: int = 100) -> list[AuditEntryRead]:
        return [AuditEntryRead(**row) for row in self.repo.audit_trail(limit)]
