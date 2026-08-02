"""Deterministic reminder + due-date logic.

Zero AI here on purpose: dates and statuses are safety-critical, so they are
computed by plain Python from *approved* records only. Key guarantees:

- A reminder is created **only** when the record has an explicit due date that
  carried supporting evidence through the extraction check. We never invent or
  infer a due date from general veterinary knowledge.
- Records with unresolved contradictions are **blocked** from generating
  reminders (the caller passes their ids).
- :func:`verify_reminder` re-checks that a generated reminder's date matches the
  approved source record — a guardrail assertion, logged.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Optional

from pawpal_ai.health_models import (
    CareStatus,
    HealthRecord,
    RecordType,
    Reminder,
    ReviewStatus,
)
from pawpal_ai.logging_setup import log_event
from pawpal_ai.textutils import parse_date

DEFAULT_OFFSETS = [30, 14, 7, 1, 0]

# Which field carries the "due" date for each record type.
_DUE_FIELD = {
    RecordType.VACCINATION: "due_date",
    RecordType.APPOINTMENT: "appointment_date",
    RecordType.MEDICATION: None,  # medications don't produce due-date reminders
}


def compute_care_status(
    due: Optional[date], today: date, due_soon_days: int = 30
) -> CareStatus:
    if due is None:
        return CareStatus.UNKNOWN
    if due < today:
        return CareStatus.OVERDUE
    if due <= today + timedelta(days=due_soon_days):
        return CareStatus.DUE_SOON
    return CareStatus.CURRENT


def _record_label(record: HealthRecord) -> str:
    name_field = {
        RecordType.VACCINATION: "vaccine_name",
        RecordType.MEDICATION: "medication_name",
        RecordType.APPOINTMENT: "purpose",
    }[record.record_type]
    name = record.fields.get(name_field) or record.record_type.value
    return f"{name} ({record.record_type.value})"


def build_reminder(
    record: HealthRecord,
    today: date,
    due_soon_days: int = 30,
    offsets: Optional[list[int]] = None,
) -> Optional[Reminder]:
    """Return a Reminder for an approved record with an explicit due date, else
    None. Refuses to build anything for unapproved records or missing due dates."""
    if record.review_status != ReviewStatus.APPROVED:
        return None
    due_field = _DUE_FIELD.get(record.record_type)
    if not due_field:
        return None
    raw = record.fields.get(due_field)
    if not raw:
        return None  # no explicit due date -> never invent one
    due = parse_date(raw)
    if due is None:
        return None

    reminder = Reminder(
        pet_id=record.pet_id,
        record_id=record.record_id,
        record_type=record.record_type,
        label=_record_label(record),
        due_date=due,
        offsets_days=offsets or list(DEFAULT_OFFSETS),
        care_status=compute_care_status(due, today, due_soon_days),
        source=record.evidence.get(due_field),
    )
    return reminder


def verify_reminder(reminder: Reminder, record: HealthRecord) -> bool:
    """Guardrail: confirm the reminder's date derives from the approved record's
    source field. Logs and returns False on mismatch (caller should not save)."""
    due_field = _DUE_FIELD.get(record.record_type)
    if not due_field:
        return False
    expected = parse_date(record.fields.get(due_field))
    ok = expected is not None and expected == reminder.due_date
    if not ok:
        log_event(
            "reminder_verification_failed",
            reminder_id=reminder.reminder_id,
            record_id=record.record_id,
        )
    return ok


def generate_reminders(
    records: Iterable[HealthRecord],
    today: date,
    due_soon_days: int = 30,
    blocked_record_ids: Optional[set[str]] = None,
    offsets: Optional[list[int]] = None,
) -> list[Reminder]:
    """Build verified reminders for all eligible approved records.

    ``blocked_record_ids`` (records in unresolved conflicts) are skipped."""
    blocked = blocked_record_ids or set()
    out: list[Reminder] = []
    for record in records:
        if record.record_id in blocked:
            log_event("reminder_blocked", record_id=record.record_id, reason="unresolved_conflict")
            continue
        reminder = build_reminder(record, today, due_soon_days, offsets)
        if reminder is None:
            continue
        if not verify_reminder(reminder, record):
            continue
        out.append(reminder)
    return out


def overdue_repeat_dates(reminder: Reminder, today: date, every_days: int = 7, count: int = 3) -> list[date]:
    """Repeated overdue alert dates once a due date has passed."""
    if reminder.care_status != CareStatus.OVERDUE:
        return []
    return [today + timedelta(days=every_days * i) for i in range(count)]
