"""Domain object <-> row conversions shared by every storage backend.

A "row" is a flat dict of column name to a JSON-friendly scalar: nested
structures (a record's fields and evidence, a reminder's source) are JSON
strings, exactly as the SQLite columns hold them. Keeping the conversion in
one place is what guarantees the SQLite and DynamoDB backends store and return
byte-identical shapes -- the repository contract tests rely on it.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

from pawpal_ai.health_models import (
    CareStatus,
    Conflict,
    HealthRecord,
    RecordType,
    Reminder,
    ReviewStatus,
    SourceEvidence,
)
from pawpal_ai.vectorstore import Chunk
from pawpal_system import Pet, Task

from api.repositories.base import Row


def pet_to_row(pet: Pet) -> Row:
    return {
        "pet_id": pet.id,
        "name": pet.name,
        "pet_type": pet.type,
        "age": pet.age,
        "age_months": pet.age_months,
        "gender": pet.gender.value,
        "color": pet.color,
    }


def task_to_row(task: Task) -> Row:
    return {
        "task_id": task.id,
        "pet_id": task.pet_id or None,
        "name": task.name,
        "category": task.category.value,
        "duration": task.duration,
        "priority": task.priority.value,
        "frequency": task.frequency.value,
        "notes": task.notes,
        "scheduled_time": task.scheduled_time,
        "due_date": task.due_date.isoformat(),
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "completed": int(task.completed),
    }


def chunk_to_row(chunk: Chunk, seq: int) -> Row:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "pet_id": chunk.pet_id,
        "seq": seq,
        "section": chunk.section,
        "text": chunk.text,
    }


def row_to_chunk(row: Row) -> Chunk:
    return Chunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        pet_id=row["pet_id"],
        text=row["text"],
        section=row["section"],
    )


def record_to_row(record: HealthRecord, document_id: str) -> Row:
    return {
        "record_id": record.record_id,
        "pet_id": record.pet_id,
        "record_type": record.record_type.value,
        "document_id": document_id,
        "fields_json": json.dumps(record.fields),
        "evidence_json": json.dumps({k: v.model_dump() for k, v in record.evidence.items()}),
        "confidence": record.confidence,
        "review_status": record.review_status.value,
        "care_status": record.care_status.value,
    }


def row_to_record(row: Row) -> HealthRecord:
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


def reminder_to_row(reminder: Reminder) -> Row:
    return {
        "reminder_id": reminder.reminder_id,
        "pet_id": reminder.pet_id,
        "record_id": reminder.record_id,
        "record_type": reminder.record_type.value,
        "label": reminder.label,
        "due_date": reminder.due_date.isoformat(),
        "offsets_json": json.dumps(reminder.offsets_days),
        "care_status": reminder.care_status.value,
        "source_json": reminder.source.model_dump_json() if reminder.source else None,
    }


def row_to_reminder(row: Row) -> Reminder:
    source: Optional[SourceEvidence] = None
    if row["source_json"]:
        source = SourceEvidence(**json.loads(row["source_json"]))
    return Reminder(
        reminder_id=row["reminder_id"],
        pet_id=row["pet_id"],
        record_id=row["record_id"],
        record_type=RecordType(row["record_type"]),
        label=row["label"],
        due_date=date.fromisoformat(row["due_date"]),
        offsets_days=json.loads(row["offsets_json"] or "[]"),
        care_status=CareStatus(row["care_status"]),
        source=source,
    )


def conflict_to_row(conflict: Conflict, conflict_id: str) -> Row:
    return {
        "conflict_id": conflict_id,
        "pet_id": conflict.pet_id,
        "record_type": conflict.record_type.value,
        "field": conflict.field,
        "value_a": conflict.value_a,
        "source_a_json": conflict.source_a.model_dump_json() if conflict.source_a else None,
        "value_b": conflict.value_b,
        "source_b_json": conflict.source_b.model_dump_json() if conflict.source_b else None,
        "resolved": int(conflict.resolved),
    }


def row_to_conflict(row: Row) -> Conflict:
    return Conflict(
        pet_id=row["pet_id"],
        record_type=RecordType(row["record_type"]),
        field=row["field"],
        value_a=row["value_a"],
        source_a=SourceEvidence(**json.loads(row["source_a_json"])) if row.get("source_a_json") else None,
        value_b=row["value_b"],
        source_b=SourceEvidence(**json.loads(row["source_b_json"])) if row.get("source_b_json") else None,
        resolved=bool(row["resolved"]),
    )


def same_conflict(row: Row, conflict: Conflict) -> bool:
    """Whether a stored conflict row is ``conflict`` -- same pet, type, field
    and pair of values in either order."""
    return (
        row["pet_id"] == conflict.pet_id
        and row["record_type"] == conflict.record_type.value
        and row["field"] == conflict.field
        and {row["value_a"], row["value_b"]} == {conflict.value_a, conflict.value_b}
    )


def strip_owner(row: Any) -> Row:
    """A row as a plain dict without its owner_id -- the snapshot shape."""
    out = dict(row)
    out.pop("owner_id", None)
    return out
