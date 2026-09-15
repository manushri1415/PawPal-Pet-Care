"""Pydantic I/O models for the health-records API surface.

Most response shapes are ``pawpal_ai.health_models`` Pydantic models used
directly (``HealthRecord``, ``Reminder``, ``ExtractionResult``, ``QAAnswer``)
-- they're already clean, storage-agnostic schemas, so wrapping them again
would just duplicate every field for no benefit (same reasoning as
``api/schemas/scheduler.py`` reusing ``pawpal_system``'s enums). Two
exceptions: ``Conflict`` has no id field of its own (the DB assigns
``conflict_id``), so ``ConflictRead`` extends it; and the audit log has no
pydantic model in pawpal_ai at all (raw dict rows), so ``AuditEntryRead`` is
new. Request bodies (``RecordUpdate``, ``AskRequest``) and small response
envelopes (``DocumentExtractResponse``, ``ScheduleCareResponse``) are new.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from pawpal_ai.health_models import Conflict, ExtractionResult, Reminder


class ConflictRead(Conflict):
    conflict_id: str


class RecordUpdate(BaseModel):
    """PATCH body: field name -> new value (or null to clear it). Only the
    given keys change; everything else on the record is left untouched."""

    fields: dict[str, Optional[str]]


class DocumentExtractResponse(BaseModel):
    document_id: str
    filename: str
    doc_type: str
    char_count: int
    injection_flagged: bool
    result: ExtractionResult


class ScheduleCareResponse(BaseModel):
    reminders: list[Reminder]
    conflicts: list[ConflictRead]
    blocked_record_ids: list[str]


class AskRequest(BaseModel):
    question: str
    document_id: Optional[str] = None


class AuditEntryRead(BaseModel):
    id: str
    event: str
    ref_id: str
    detail: str
    created_at: str
