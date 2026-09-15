"""GET/POST /api/pets, GET/PATCH/DELETE /api/pets/{pet_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_scheduler_service
from api.schemas.scheduler import PetCreate, PetRead, PetUpdate
from api.services.scheduler_service import PetHasHealthRecordsError, SchedulerService

router = APIRouter(prefix="/api/pets", tags=["pets"])


@router.get("", response_model=list[PetRead])
def list_pets(service: SchedulerService = Depends(get_scheduler_service)) -> list[PetRead]:
    return service.list_pets()


@router.post("", response_model=PetRead, status_code=201)
def create_pet(
    data: PetCreate, service: SchedulerService = Depends(get_scheduler_service)
) -> PetRead:
    try:
        return service.create_pet(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/{pet_id}", response_model=PetRead)
def get_pet(pet_id: str, service: SchedulerService = Depends(get_scheduler_service)) -> PetRead:
    pet = service.get_pet(pet_id)
    if pet is None:
        raise HTTPException(status_code=404, detail="Pet not found")
    return pet


@router.patch("/{pet_id}", response_model=PetRead)
def update_pet(
    pet_id: str, patch: PetUpdate, service: SchedulerService = Depends(get_scheduler_service)
) -> PetRead:
    try:
        pet = service.update_pet(pet_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if pet is None:
        raise HTTPException(status_code=404, detail="Pet not found")
    return pet


@router.delete("/{pet_id}", status_code=204)
def delete_pet(
    pet_id: str,
    force: bool = Query(default=False),
    service: SchedulerService = Depends(get_scheduler_service),
) -> None:
    try:
        result = service.delete_pet(pet_id, force=force)
    except PetHasHealthRecordsError as e:
        raise HTTPException(
            status_code=409, detail=f"{e.count} health record(s) exist; pass ?force=true"
        ) from e
    if result is None:
        raise HTTPException(status_code=404, detail="Pet not found")
