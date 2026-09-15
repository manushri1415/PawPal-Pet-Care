"""Task CRUD + complete/uncomplete/overlaps.

Route order matters here: /overlaps must be registered before /{task_id} so
Starlette doesn't match "overlaps" as a task_id path parameter.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.clock import ClientClock, get_client_clock
from api.deps import get_scheduler_service
from api.schemas.scheduler import (
    OverlapsResponse,
    TaskCompleteResponse,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from api.services.scheduler_service import SchedulerService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
def list_tasks(
    pet_id: Optional[str] = Query(default=None),
    status: str = Query(default="open", pattern="^(open|completed|all)$"),
    sort: Optional[str] = Query(default=None, pattern="^(priority|time|duration)$"),
    service: SchedulerService = Depends(get_scheduler_service),
) -> list[TaskRead]:
    return service.list_tasks(pet_id=pet_id, status=status, sort=sort)


@router.get("/overlaps", response_model=OverlapsResponse)
def get_overlaps(service: SchedulerService = Depends(get_scheduler_service)) -> OverlapsResponse:
    return service.get_overlaps()


@router.post("", response_model=TaskRead, status_code=201)
def create_task(
    data: TaskCreate,
    service: SchedulerService = Depends(get_scheduler_service),
    clock: ClientClock = Depends(get_client_clock),
) -> TaskRead:
    try:
        return service.create_task(data, clock)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: str, service: SchedulerService = Depends(get_scheduler_service)) -> TaskRead:
    task = service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: str,
    patch: TaskUpdate,
    service: SchedulerService = Depends(get_scheduler_service),
    clock: ClientClock = Depends(get_client_clock),
) -> TaskRead:
    try:
        task = service.update_task(task_id, patch, clock)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, service: SchedulerService = Depends(get_scheduler_service)) -> None:
    if not service.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")


@router.post("/{task_id}/complete", response_model=TaskCompleteResponse)
def complete_task(
    task_id: str, service: SchedulerService = Depends(get_scheduler_service)
) -> TaskCompleteResponse:
    result = service.complete_task(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post("/{task_id}/uncomplete", response_model=TaskRead)
def uncomplete_task(
    task_id: str, service: SchedulerService = Depends(get_scheduler_service)
) -> TaskRead:
    task = service.uncomplete_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
