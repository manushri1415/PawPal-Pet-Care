"""Guardrail helpers gathered in one place.

Most guardrails live where they act (document validation in ``documents.py``,
evidence grounding in ``evidence.py``, reminder verification in ``reminders.py``).
This module holds the cross-cutting checks the app and eval call explicitly, so
"the guardrails" are easy to point at for the rubric.
"""

from __future__ import annotations

import re

from pawpal_ai.health_models import HealthRecord, ReviewStatus
from pawpal_ai.logging_setup import log_event

# Requests we must refuse: diagnosis / prescription / new-treatment advice.
_ADVICE_RE = re.compile(
    r"\b(diagnos\w*|what'?s wrong with|should i (give|administer|use)|"
    r"prescrib\w*|what (medicine|dose|dosage) should|is it safe to give|"
    r"recommend a treatment|treat (my|the) )\b",
    re.IGNORECASE,
)


def is_medical_advice_request(question: str) -> bool:
    """True if the question asks for diagnosis/prescription/treatment advice."""
    flagged = bool(_ADVICE_RE.search(question or ""))
    if flagged:
        log_event("advice_refused", reason="medical_advice_request")
    return flagged


REFUSAL_MESSAGE = (
    "I can only organize and explain your pet's existing records — I can't diagnose, "
    "prescribe, or recommend new treatment. Please consult your veterinarian."
)


def can_save_record(record: HealthRecord) -> bool:
    """Approval guardrail: only APPROVED records may be persisted/scheduled.

    Returns False (and logs) for anything not explicitly human-approved. The
    storage layer still records rejected/pending rows for the audit trail, but
    the app uses this gate before generating reminders."""
    ok = record.review_status == ReviewStatus.APPROVED
    if not ok:
        log_event("save_blocked", record_id=record.record_id, status=record.review_status.value)
    return ok


def assert_no_ungrounded_fields(record: HealthRecord) -> list[str]:
    """Return the names of any non-null field lacking evidence (should be empty
    after the extraction check — this is a defensive re-assertion)."""
    bad = [
        name
        for name, value in record.fields.items()
        if value is not None and name not in record.evidence
    ]
    if bad:
        log_event("ungrounded_fields_detected", record_id=record.record_id, fields=len(bad))
    return bad
