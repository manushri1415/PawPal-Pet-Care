"""Pydantic schemas for PawPal AI health records, evidence, and reminders.

These are the contract between the LLM (which proposes structured records) and
the deterministic Python that validates, stores, and schedules them. Two design
rules the whole system leans on:

1. **Every clinical field is optional** (``| None``). The model is instructed to
   emit ``null`` when a value is not present in the source, and the deterministic
   evidence check nulls anything it cannot ground. This is how we guarantee the
   system never *invents* a due date, dosage, or frequency.
2. **Every extracted field carries its source.** ``evidence`` maps field name ->
   :class:`SourceEvidence` so every stored value is traceable to a document
   chunk (the citation requirement).
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CareStatus(str, Enum):
    CURRENT = "current"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    UNKNOWN = "unknown"


class RecordType(str, Enum):
    VACCINATION = "vaccination"
    MEDICATION = "medication"
    APPOINTMENT = "appointment"


class SourceEvidence(BaseModel):
    """A citation: where in which document a field's value came from."""

    document_id: str
    chunk_id: str
    section: Optional[str] = None  # page/section/paragraph identifier
    supporting_text: str = ""  # the quoted span from the source
    match_score: float = 0.0  # 0..1 how well the field value is grounded


class HealthRecord(BaseModel):
    """Base for all extracted records. ``fields`` holds the clinical values so
    subclasses stay uniform for storage, evidence-mapping, and review."""

    record_id: str = ""
    pet_id: str = ""
    record_type: RecordType
    fields: dict[str, Optional[str]] = Field(default_factory=dict)
    evidence: dict[str, SourceEvidence] = Field(default_factory=dict)
    confidence: float = 0.0
    review_status: ReviewStatus = ReviewStatus.PENDING
    care_status: CareStatus = CareStatus.UNKNOWN

    def grounded_fields(self) -> dict[str, str]:
        """Non-null fields that have supporting evidence attached."""
        return {
            k: v
            for k, v in self.fields.items()
            if v is not None and k in self.evidence
        }


# --- LLM-facing extraction schemas (what the model is asked to fill in) -------
# These are intentionally flat and string-typed so ``messages.parse`` /
# structured output stays reliable across models. Deterministic Python parses
# dates and validates afterwards.


class ExtractedVaccination(BaseModel):
    vaccine_name: Optional[str] = None
    administered_date: Optional[str] = None  # ISO date string or null
    due_date: Optional[str] = None  # only if explicit in the document
    clinic: Optional[str] = None
    veterinarian: Optional[str] = None


class ExtractedMedication(BaseModel):
    medication_name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    clinic: Optional[str] = None


class ExtractedAppointment(BaseModel):
    purpose: Optional[str] = None
    appointment_date: Optional[str] = None
    clinic: Optional[str] = None


class ExtractionEnvelope(BaseModel):
    """Top-level structured output the LLM must return.

    ``pet_name`` lets us catch wrong/missing pet attributions. Lists may be
    empty — an empty extraction is a valid answer (the model must not pad it).
    """

    pet_name: Optional[str] = None
    vaccinations: list[ExtractedVaccination] = Field(default_factory=list)
    medications: list[ExtractedMedication] = Field(default_factory=list)
    appointments: list[ExtractedAppointment] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Outcome of the agentic extraction loop, handed to human review."""

    records: list[HealthRecord] = Field(default_factory=list)
    unsupported_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    pet_name_in_document: Optional[str] = None
    attempts: int = 0
    injection_flagged: bool = False
    notes: list[str] = Field(default_factory=list)


class Conflict(BaseModel):
    """A detected contradiction between two records for the same pet."""

    pet_id: str
    record_type: RecordType
    field: str
    value_a: str
    source_a: Optional[SourceEvidence] = None
    value_b: str
    source_b: Optional[SourceEvidence] = None
    resolved: bool = False


class Reminder(BaseModel):
    """A deterministic reminder derived from an *approved* record's due date."""

    reminder_id: str = ""
    pet_id: str
    record_id: str
    record_type: RecordType
    label: str
    due_date: date
    offsets_days: list[int] = Field(default_factory=lambda: [30, 14, 7, 1, 0])
    care_status: CareStatus = CareStatus.UNKNOWN
    source: Optional[SourceEvidence] = None


class QAAnswer(BaseModel):
    """A retrieval-grounded answer to a user question about the documents."""

    question: str
    answer: str
    abstained: bool = False
    refused: bool = False
    citations: list[SourceEvidence] = Field(default_factory=list)
