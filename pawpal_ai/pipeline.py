"""High-level orchestration used by both the Streamlit app and the eval harness.

Ties the pieces together so callers don't repeat the wiring:

    ingest -> chunk+index (shared store) -> agentic extract -> (human review) ->
    approve -> conflict scan -> reminders

Nothing here saves records without approval; approval is an explicit call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from pawpal_ai.config import Settings, get_settings
from pawpal_ai.contradictions import conflicted_record_ids, detect_conflicts
from pawpal_ai.documents import DocumentResult
from pawpal_ai.extraction_agent import Tracer, append_trace, extract_records
from pawpal_ai.health_models import (
    Conflict,
    ExtractionResult,
    HealthRecord,
    Reminder,
    ReviewStatus,
)
from pawpal_ai.llm import LLMClient, build_llm
from pawpal_ai.reminders import generate_reminders
from pawpal_ai.vectorstore import VectorStore


def new_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:10]}"


@dataclass
class ProcessedDocument:
    document_id: str
    result: ExtractionResult
    tracer: Tracer


def process_document(
    doc: DocumentResult,
    pet_id: str,
    llm: LLMClient,
    settings: Optional[Settings] = None,
    *,
    store: Optional[VectorStore] = None,
    document_id: Optional[str] = None,
    use_fewshot: bool = True,
    write_trace: bool = False,
) -> ProcessedDocument:
    """Ingest+extract one document. Records come back PENDING review."""
    settings = settings or get_settings()
    document_id = document_id or new_document_id()
    tracer = Tracer.for_document(doc, document_id)
    result = extract_records(
        doc,
        pet_id=pet_id,
        llm=llm,
        document_id=document_id,
        k=settings.retrieval_k,
        max_attempts=settings.max_attempts,
        evidence_threshold=settings.evidence_threshold,
        use_fewshot=use_fewshot,
        tracer=tracer,
        store=store,
    )
    if write_trace:
        append_trace(tracer)
    return ProcessedDocument(document_id=document_id, result=result, tracer=tracer)


def approve_and_schedule(
    approved_records: list[HealthRecord],
    today: Optional[date] = None,
    settings: Optional[Settings] = None,
) -> tuple[list[Reminder], list[Conflict], set[str]]:
    """Given human-approved records, detect conflicts and generate reminders.

    Reminders are blocked for records that are in an unresolved conflict.
    Returns (reminders, conflicts, blocked_record_ids)."""
    settings = settings or get_settings()
    today = today or date.today()
    for rec in approved_records:
        rec.review_status = ReviewStatus.APPROVED
    conflicts = detect_conflicts(approved_records)
    blocked = conflicted_record_ids(approved_records)
    reminders = generate_reminders(
        approved_records,
        today=today,
        due_soon_days=settings.due_soon_days,
        blocked_record_ids=blocked,
    )
    return reminders, conflicts, blocked


def make_llm(settings: Optional[Settings] = None) -> LLMClient:
    return build_llm(settings or get_settings())
