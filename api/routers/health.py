"""Health-records API: documents/extraction (gated), review, reminders &
conflicts, ask (gated), and audit -- see MIGRATION_PLAN.md §3.

Extraction and Ask are the only two LLM-calling (cost-incurring) endpoints,
so they're the only two behind ``require_owner`` (§4). Everything else --
review, reminders/conflicts, audit -- is free: a public demo visitor can
browse and manage already-extracted records, just never trigger a new model
call.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from api.clock import ClientClock, get_client_clock
from api.deps import get_health_service, require_owner
from api.schemas.health import (
    AskRequest,
    AuditEntryRead,
    ConflictRead,
    DocumentExtractResponse,
    RecordUpdate,
    ScheduleCareResponse,
)
from api.services.health_service import DocumentRejected, HealthService
from pawpal_ai.health_models import HealthRecord, QAAnswer, Reminder, ReviewStatus

router = APIRouter(prefix="/api/health", tags=["health"])


def _require_pet(pet_id: str, service: HealthService) -> None:
    if not service.pet_exists(pet_id):
        raise HTTPException(status_code=404, detail="Pet not found")


# -- documents / extraction (🔒 AI-gated) -------------------------------------


@router.post(
    "/pets/{pet_id}/documents:extract",
    response_model=DocumentExtractResponse,
    dependencies=[Depends(require_owner)],
)
def extract_document(
    pet_id: str,
    file: Optional[UploadFile] = File(default=None),
    text: Optional[str] = Form(default=None),
    service: HealthService = Depends(get_health_service),
) -> DocumentExtractResponse:
    _require_pet(pet_id, service)
    try:
        if file is not None:
            return service.extract_from_upload(pet_id, file.file.read(), file.filename or "upload")
        if text and text.strip():
            return service.extract_from_text(pet_id, text)
        raise HTTPException(status_code=422, detail="Upload a file or provide text.")
    except DocumentRejected as e:
        # Only an ingestion rejection is echoed back. Any other exception is a
        # server fault whose text is not the client's to see -- see
        # DocumentRejected for why a bare `except ValueError` here was a leak.
        raise HTTPException(status_code=422, detail=str(e)) from e


# -- review (free) -------------------------------------------------------------


@router.get("/pets/{pet_id}/records", response_model=list[HealthRecord])
def list_records(
    pet_id: str,
    review_status: Optional[ReviewStatus] = Query(default=None),
    service: HealthService = Depends(get_health_service),
) -> list[HealthRecord]:
    _require_pet(pet_id, service)
    return service.list_records(pet_id, review_status)


@router.get("/records/{record_id}", response_model=HealthRecord)
def get_record(record_id: str, service: HealthService = Depends(get_health_service)) -> HealthRecord:
    record = service.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.post("/records/{record_id}/approve", response_model=HealthRecord)
def approve_record(
    record_id: str, service: HealthService = Depends(get_health_service)
) -> HealthRecord:
    record = service.approve_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.post("/records/{record_id}/reject", response_model=HealthRecord)
def reject_record(
    record_id: str, service: HealthService = Depends(get_health_service)
) -> HealthRecord:
    record = service.reject_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.patch("/records/{record_id}", response_model=HealthRecord)
def update_record(
    record_id: str, patch: RecordUpdate, service: HealthService = Depends(get_health_service)
) -> HealthRecord:
    record = service.update_record(record_id, patch)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


# -- reminders & conflicts (free) ----------------------------------------------


@router.post("/pets/{pet_id}/schedule-care", response_model=ScheduleCareResponse)
def schedule_care(
    pet_id: str,
    service: HealthService = Depends(get_health_service),
    clock: ClientClock = Depends(get_client_clock),
) -> ScheduleCareResponse:
    _require_pet(pet_id, service)
    return service.schedule_care(pet_id, today=clock.today)


@router.get("/pets/{pet_id}/reminders", response_model=list[Reminder])
def list_reminders(pet_id: str, service: HealthService = Depends(get_health_service)) -> list[Reminder]:
    _require_pet(pet_id, service)
    return service.list_reminders(pet_id)


@router.get("/pets/{pet_id}/conflicts", response_model=list[ConflictRead])
def list_conflicts(
    pet_id: str,
    unresolved_only: bool = Query(default=False),
    service: HealthService = Depends(get_health_service),
) -> list[ConflictRead]:
    _require_pet(pet_id, service)
    return service.list_conflicts(pet_id, unresolved_only)


@router.post("/conflicts/{conflict_id}/resolve", response_model=ConflictRead)
def resolve_conflict(
    conflict_id: str, service: HealthService = Depends(get_health_service)
) -> ConflictRead:
    conflict = service.resolve_conflict(conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return conflict


# -- ask (🔒 AI-gated) ----------------------------------------------------------


@router.post("/pets/{pet_id}/ask", response_model=QAAnswer, dependencies=[Depends(require_owner)])
def ask(
    pet_id: str, body: AskRequest, service: HealthService = Depends(get_health_service)
) -> QAAnswer:
    _require_pet(pet_id, service)
    return service.ask(pet_id, body.question, body.document_id)


# -- audit (free) ---------------------------------------------------------------


@router.get("/audit", response_model=list[AuditEntryRead])
def audit_trail(
    limit: int = Query(default=50, ge=1, le=500), service: HealthService = Depends(get_health_service)
) -> list[AuditEntryRead]:
    return service.audit_trail(limit)
