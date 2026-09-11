"""Deterministic contradiction detection across a pet's records.

When multiple documents describe the same vaccine or medication, they can
disagree (a re-issued certificate with a different date, a corrected dosage).
We never silently pick a winner — we surface the conflict with both values and
their sources so a human decides, and the reminder engine blocks reminders for
records involved in an unresolved conflict.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pawpal_ai.health_models import Conflict, HealthRecord, RecordType, SourceEvidence
from pawpal_ai.textutils import normalize_text, parse_date

# Fields compared for each record type, and whether they are date-typed.
_COMPARE_FIELDS = {
    RecordType.VACCINATION: [("administered_date", True), ("due_date", True)],
    RecordType.MEDICATION: [("dosage", False), ("frequency", False)],
    RecordType.APPOINTMENT: [("appointment_date", True)],
}

_NAME_FIELD = {
    RecordType.VACCINATION: "vaccine_name",
    RecordType.MEDICATION: "medication_name",
    RecordType.APPOINTMENT: "purpose",
}

_DATE_TOLERANCE_DAYS = 1


def _key(record: HealthRecord) -> Optional[str]:
    name = record.fields.get(_NAME_FIELD[record.record_type])
    return normalize_text(name) if name else None


def _values_conflict(field_is_date: bool, a: str, b: str) -> bool:
    if field_is_date:
        da, db = parse_date(a), parse_date(b)
        if da is None or db is None:
            return normalize_text(a) != normalize_text(b)
        return abs((da - db).days) > _DATE_TOLERANCE_DAYS
    return normalize_text(a) != normalize_text(b)


def _bucket(records: list[HealthRecord]) -> dict[tuple[str, RecordType, str], list[HealthRecord]]:
    """Group records by (pet_id, record_type, normalized name).

    ``pet_id`` is part of the key -- not just ``record_type``/name -- so this
    grouping is safe on its own even if a future caller passes records
    spanning more than one pet: two different pets' "Rabies" vaccinations
    must never be compared against each other. Today's only caller
    (``pages/1_Health_Records.py``) already pre-filters to one pet before
    calling in, but that isolation shouldn't have to live only in the caller
    (see UPGRADES.md #1.6). Shared by both functions below so a fix here
    can't be applied to only one copy.
    """
    buckets: dict[tuple[str, RecordType, str], list[HealthRecord]] = {}
    for rec in records:
        key = _key(rec)
        if key is None:
            continue
        buckets.setdefault((rec.pet_id, rec.record_type, key), []).append(rec)
    return buckets


def detect_conflicts(records: list[HealthRecord]) -> list[Conflict]:
    """Compare same-pet, same-type, same-name records pairwise and report
    disagreements."""
    conflicts: list[Conflict] = []
    for (_pet_id, record_type, _name), group in _bucket(records).items():
        if len(group) < 2:
            continue
        for field_name, is_date in _COMPARE_FIELDS[record_type]:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    va = group[i].fields.get(field_name)
                    vb = group[j].fields.get(field_name)
                    if not va or not vb:
                        continue
                    if _values_conflict(is_date, va, vb):
                        conflicts.append(
                            Conflict(
                                pet_id=group[i].pet_id,
                                record_type=record_type,
                                field=field_name,
                                value_a=va,
                                source_a=group[i].evidence.get(field_name),
                                value_b=vb,
                                source_b=group[j].evidence.get(field_name),
                            )
                        )
    return conflicts


def conflicted_record_ids(records: list[HealthRecord]) -> set[str]:
    """Ids of records that participate in at least one conflict (for blocking
    reminders). Recomputed from the records' field values."""
    ids: set[str] = set()
    for (_pet_id, record_type, _name), group in _bucket(records).items():
        if len(group) < 2:
            continue
        for field_name, is_date in _COMPARE_FIELDS[record_type]:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    va, vb = group[i].fields.get(field_name), group[j].fields.get(field_name)
                    if va and vb and _values_conflict(is_date, va, vb):
                        ids.add(group[i].record_id)
                        ids.add(group[j].record_id)
    return ids
