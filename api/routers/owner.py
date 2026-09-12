"""GET/PATCH /api/owner — singleton owner profile + work-schedule settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_scheduler_service
from api.schemas.scheduler import OwnerRead, OwnerUpdate
from api.services.scheduler_service import SchedulerService

router = APIRouter(prefix="/api/owner", tags=["owner"])


@router.get("", response_model=OwnerRead)
def get_owner(service: SchedulerService = Depends(get_scheduler_service)) -> OwnerRead:
    return service.get_owner()


@router.patch("", response_model=OwnerRead)
def update_owner(
    patch: OwnerUpdate, service: SchedulerService = Depends(get_scheduler_service)
) -> OwnerRead:
    try:
        return service.update_owner(patch)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
