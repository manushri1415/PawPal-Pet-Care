"""POST /api/schedule/generate — stateless, always computed live from current tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import get_scheduler_service
from api.schemas.scheduler import ScheduleGenerateResponse
from api.services.scheduler_service import SchedulerService

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.post("/generate", response_model=ScheduleGenerateResponse)
def generate_schedule(
    date: Optional[datetime] = Query(default=None),
    service: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleGenerateResponse:
    return service.generate_schedule(date)
