"""The agentic extraction workflow: plan -> act -> check -> revise.

This is the multi-step "agent" the project centers on. It does NOT just call the
LLM once. Each attempt:

1. **Plan**  — choose retrieval queries for the concepts we want (vaccines,
   meds, appointments).
2. **Act**   — retrieve passages from the local vector store and ask the LLM for
   structured output grounded in them.
3. **Check** — deterministically validate: schema (Pydantic, already enforced by
   the typed return), then *field-level evidence* (drop anything not supported
   by a retrieved passage), then detect missing/unsupported fields.
4. **Revise**— if the check found nothing usable, re-prompt with specific
   feedback, up to ``max_attempts``; then stop and hand results to human review.

Every step is recorded in a :class:`Tracer` whose transcript is appended to
``ai_interactions.md``, a committed log of what the agent actually did on each
run. The result is a set of PENDING records — nothing is trusted until a human
approves.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from pawpal_ai.documents import DocumentResult
from pawpal_ai.evidence import find_evidence
from pawpal_ai.health_models import (
    ExtractionResult,
    HealthRecord,
    RecordType,
    ReviewStatus,
    SourceEvidence,
)
from pawpal_ai.chunking import chunk_text
from pawpal_ai.llm import LLMClient, LLMError
from pawpal_ai.logging_setup import log_event
from pawpal_ai.vectorstore import RetrievedChunk, VectorStore

# Retrieval "plan": queries chosen to surface each concept.
_CONCEPT_QUERIES = {
    "vaccination": "vaccine vaccination rabies distemper administered due date booster",
    "medication": "medication drug dosage mg tablet frequency daily duration",
    "appointment": "follow-up recheck appointment wellness exam scheduled date",
}


def _redact_filename(filename: str) -> str:
    """Replace a possibly-identifying filename with a stable, generic label.

    ``ai_interactions.md`` is committed to the repo, so whatever an uploader
    typed/exported as their filename must never land in it verbatim (a
    vet-portal "download my documents" export, for instance, names the file
    after the patient/owner). Keep the extension for readability and hash the
    rest so repeat runs on the same file still correlate in the trace.
    """
    digest = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:10]
    suffix = Path(filename).suffix
    return f"document-{digest}{suffix}"


@dataclass
class Tracer:
    """Collects human-readable steps for the ai_interactions.md transcript."""

    title: str
    steps: list[str] = field(default_factory=list)

    @classmethod
    def for_document(cls, doc: DocumentResult, document_id: str) -> "Tracer":
        """Build a Tracer titled from ``doc``, with the filename redacted.

        This is the single place both call sites (direct ``extract_records``
        use and :func:`pawpal_ai.pipeline.process_document`) construct a
        Tracer, so the redaction can't be implemented in one path and
        forgotten in the other.
        """
        title = _redact_filename(doc.filename) if doc.filename else document_id
        return cls(title=title)

    def step(self, text: str) -> None:
        self.steps.append(text)

    def to_markdown(self) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"## Extraction trace — {self.title} ({stamp})", ""]
        lines += [f"{i + 1}. {s}" for i, s in enumerate(self.steps)]
        return "\n".join(lines) + "\n"


def append_trace(tracer: Tracer, md_path: str | Path = "ai_interactions.md") -> None:
    """Append a trace to the committed reasoning-trace file."""
    p = Path(md_path)
    with p.open("a", encoding="utf-8") as fh:
        fh.write("\n" + tracer.to_markdown())


def _plan_queries() -> dict[str, str]:
    return dict(_CONCEPT_QUERIES)


def _retrieve_all(
    store: VectorStore, k: int, document_id: str, pet_id: str
) -> list[RetrievedChunk]:
    """Union of top-k retrievals across every concept query (dedup by chunk)."""
    seen: dict[str, RetrievedChunk] = {}
    for query in _plan_queries().values():
        for rc in store.retrieve(query, k=k, document_id=document_id, pet_id=pet_id):
            prev = seen.get(rc.chunk.chunk_id)
            if prev is None or rc.score > prev.score:
                seen[rc.chunk.chunk_id] = rc
    return sorted(seen.values(), key=lambda r: -r.score)


def _fields_of(record_type: RecordType, item) -> dict[str, Optional[str]]:
    if record_type == RecordType.VACCINATION:
        return {
            "vaccine_name": item.vaccine_name,
            "administered_date": item.administered_date,
            "due_date": item.due_date,
            "clinic": item.clinic,
            "veterinarian": item.veterinarian,
        }
    if record_type == RecordType.MEDICATION:
        return {
            "medication_name": item.medication_name,
            "dosage": item.dosage,
            "frequency": item.frequency,
            "duration": item.duration,
            "clinic": item.clinic,
        }
    return {
        "purpose": item.purpose,
        "appointment_date": item.appointment_date,
        "clinic": item.clinic,
    }


def _name_field(record_type: RecordType) -> str:
    return {
        RecordType.VACCINATION: "vaccine_name",
        RecordType.MEDICATION: "medication_name",
        RecordType.APPOINTMENT: "purpose",
    }[record_type]


def _build_record(
    record_type: RecordType,
    item,
    pet_id: str,
    chunks: list[RetrievedChunk],
    threshold: float,
    unsupported: list[str],
) -> Optional[HealthRecord]:
    """Turn one extracted item into a grounded HealthRecord, nulling any field
    that lacks supporting evidence. Returns None if even the name is unsupported
    (i.e. the whole item looks hallucinated)."""
    raw = _fields_of(record_type, item)
    grounded: dict[str, Optional[str]] = {}
    evidence: dict[str, SourceEvidence] = {}
    scores: list[float] = []

    for fname, value in raw.items():
        if value is None or not str(value).strip():
            grounded[fname] = None
            continue
        ev = find_evidence(fname, str(value), chunks, threshold=threshold)
        if ev is None:
            grounded[fname] = None  # UNSUPPORTED -> dropped
            unsupported.append(f"{record_type.value}.{fname}={value!r}")
            log_event("unsupported_field_removed", field=fname, record_type=record_type.value)
        else:
            grounded[fname] = str(value)
            evidence[fname] = ev
            scores.append(ev.match_score)

    name_field = _name_field(record_type)
    if grounded.get(name_field) is None:
        return None  # nothing to anchor the record on

    confidence = round(sum(scores) / len(scores), 3) if scores else 0.0
    return HealthRecord(
        record_id=f"rec_{uuid.uuid4().hex[:12]}",
        pet_id=pet_id,
        record_type=record_type,
        fields=grounded,
        evidence=evidence,
        confidence=confidence,
        review_status=ReviewStatus.PENDING,
    )


def _missing_fields(records: list[HealthRecord]) -> list[str]:
    """Report clinically-important fields that came back null (for review)."""
    important = {
        RecordType.VACCINATION: ["administered_date", "due_date"],
        RecordType.MEDICATION: ["dosage", "frequency"],
        RecordType.APPOINTMENT: ["appointment_date"],
    }
    out: list[str] = []
    for rec in records:
        for f in important.get(rec.record_type, []):
            if rec.fields.get(f) is None:
                name = rec.fields.get(_name_field(rec.record_type), "?")
                out.append(f"{rec.record_type.value}[{name}].{f}")
    return out


def extract_records(
    doc: DocumentResult,
    pet_id: str,
    llm: LLMClient,
    *,
    document_id: str,
    k: int = 4,
    max_attempts: int = 3,
    evidence_threshold: float = 0.5,
    use_fewshot: bool = True,
    tracer: Optional[Tracer] = None,
    store: Optional[VectorStore] = None,
) -> ExtractionResult:
    """Run the plan-act-check loop over one ingested document.

    If ``store`` is provided, this document's chunks are added to it (so a shared
    store can serve later Q&A across documents); otherwise a private store is
    built for this call only."""
    tracer = tracer or Tracer.for_document(doc, document_id)
    log_event("extraction_started", document_id=document_id, provider=getattr(llm, "provider", "?"))

    chunks = chunk_text(doc.text, document_id, pet_id)
    if store is None:
        store = VectorStore()
    store.add(chunks)
    tracer.step(f"PLAN: chunked document into {len(chunks)} chunks; queries = {list(_plan_queries())}")
    if doc.injection_flagged:
        tracer.step(f"GUARDRAIL: prompt-injection patterns flagged ({len(doc.injection_spans)}); treating text as untrusted data.")

    retrieved = _retrieve_all(store, k=k, document_id=document_id, pet_id=pet_id)
    tracer.step(
        "ACT: retrieved chunks "
        + str([rc.chunk.chunk_id for rc in retrieved])
        + " (retrieval drives what the model sees)"
    )
    log_event("retrieval", document_id=document_id, chunk_ids=[rc.chunk.chunk_id for rc in retrieved], k=k)

    records: list[HealthRecord] = []
    unsupported: list[str] = []
    errors: list[str] = []
    fatal_error: Optional[str] = None
    envelope = None
    feedback = ""
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            envelope = llm.extract(retrieved, use_fewshot=use_fewshot, feedback=feedback)
        except LLMError as exc:
            message = str(exc)
            errors.append(message)
            tracer.step(f"ACT attempt {attempt}: LLM error: {message}")
            log_event("extraction_error", attempt=attempt, error=str(exc)[:80])
            if not getattr(exc, "retryable", True):
                fatal_error = message
                tracer.step("STOP: non-retryable LLM error; handing an empty result to review.")
                log_event("retry_limit_reached", attempts=attempt, reason="non_retryable_llm_error")
                break
            feedback = "Previous attempt failed to return valid structured output. Return valid JSON."
            if attempt >= max_attempts:
                fatal_error = message
                tracer.step("STOP: retry limit reached after LLM errors; handing an empty result to review.")
                log_event("retry_limit_reached", attempts=attempt)
                break
            continue

        unsupported = []
        records = []
        for item in envelope.vaccinations:
            rec = _build_record(RecordType.VACCINATION, item, pet_id, retrieved, evidence_threshold, unsupported)
            if rec:
                records.append(rec)
        for item in envelope.medications:
            rec = _build_record(RecordType.MEDICATION, item, pet_id, retrieved, evidence_threshold, unsupported)
            if rec:
                records.append(rec)
        for item in envelope.appointments:
            rec = _build_record(RecordType.APPOINTMENT, item, pet_id, retrieved, evidence_threshold, unsupported)
            if rec:
                records.append(rec)

        tracer.step(
            f"CHECK attempt {attempt}: {len(records)} grounded record(s); "
            f"{len(unsupported)} unsupported field(s) dropped."
        )

        # A valid outcome: at least one grounded record, OR the model correctly
        # found nothing (empty document / irrelevant content). Both stop the loop.
        if records or not any([envelope.vaccinations, envelope.medications, envelope.appointments]):
            break
        feedback = (
            "Some values could not be grounded in the passages. Only extract values "
            "explicitly present; use null otherwise."
        )
        tracer.step(f"REVISE: re-prompting (attempt {attempt} produced only unsupported values).")

    missing = _missing_fields(records)
    if missing:
        tracer.step(f"CHECK: missing important fields -> {missing}")
    tracer.step(
        f"DONE: {len(records)} record(s) PENDING human review after {attempts} attempt(s)."
    )
    log_event("extraction_completed", document_id=document_id, records=len(records), attempts=attempts)

    return ExtractionResult(
        records=records,
        unsupported_fields=unsupported,
        missing_fields=missing,
        errors=errors,
        fatal_error=fatal_error,
        pet_name_in_document=envelope.pet_name if envelope else None,
        attempts=attempts,
        injection_flagged=doc.injection_flagged,
        notes=list(tracer.steps),
    )
