"""Pydantic I/O models for the scheduler API surface (owner/pets/tasks/schedule).

Field types mirror pawpal_system.py's domain objects 1:1 — reusing the same
Enum classes (Category/Priority/Frequency/Gender) as the single source of
truth for allowed values, rather than duplicating them as string literals.
Health-records schemas land in Phase 3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from pawpal_system import Category, Frequency, Gender, Priority

# -- Owner --------------------------------------------------------------------


class OwnerRead(BaseModel):
    owner_id: str
    name: str
    email: str = ""
    phone_number: str = ""
    available_hours_per_day: float
    work_start_hour: int
    work_start_minute: int
    work_end_hour: int
    work_end_minute: int
    break_between_tasks_minutes: int


class OwnerUpdate(BaseModel):
    """All fields optional — PATCH semantics, only supplied fields change."""

    name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    available_hours_per_day: Optional[float] = None
    work_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    work_start_minute: Optional[int] = Field(default=None, ge=0, le=59)
    work_end_hour: Optional[int] = Field(default=None, ge=0, le=23)
    work_end_minute: Optional[int] = Field(default=None, ge=0, le=59)
    break_between_tasks_minutes: Optional[int] = Field(default=None, ge=0)


# -- Pets -----------------------------------------------------------------------


class PetRead(BaseModel):
    pet_id: str
    owner_id: str
    name: str
    pet_type: str
    age: int
    age_months: int
    gender: Gender
    color: str = ""


class PetCreate(BaseModel):
    name: str
    pet_type: str
    age: int = Field(ge=0)
    age_months: int = Field(default=0, ge=0)
    gender: Gender = Gender.UNKNOWN
    color: str = ""


class PetUpdate(BaseModel):
    name: Optional[str] = None
    pet_type: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0)
    age_months: Optional[int] = Field(default=None, ge=0)
    gender: Optional[Gender] = None
    color: Optional[str] = None


# -- Tasks ----------------------------------------------------------------------


class TaskRead(BaseModel):
    task_id: str
    owner_id: str
    pet_id: Optional[str] = None
    name: str
    category: Category
    duration: int
    priority: Priority
    frequency: Frequency
    notes: str = ""
    scheduled_time: str = ""
    due_date: datetime
    end_date: Optional[datetime] = None
    completed: bool


class TaskCreate(BaseModel):
    name: str
    category: Category
    pet_id: Optional[str] = None
    duration: int = Field(ge=0)
    priority: Priority = Priority.MEDIUM
    frequency: Frequency = Frequency.ONCE
    notes: str = ""
    scheduled_time: str = ""
    due_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[Category] = None
    pet_id: Optional[str] = None
    duration: Optional[int] = Field(default=None, ge=0)
    priority: Optional[Priority] = None
    frequency: Optional[Frequency] = None
    notes: Optional[str] = None
    scheduled_time: Optional[str] = None
    due_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class TaskCompleteResponse(BaseModel):
    task: TaskRead
    next_occurrence: Optional[TaskRead] = None


# -- Schedule / overlaps ---------------------------------------------------------


class ScheduledItem(BaseModel):
    task: TaskRead
    start: datetime
    end: datetime


class ScheduleGenerateResponse(BaseModel):
    schedule: list[ScheduledItem]
    conflicts: list[str]


class OverlapsResponse(BaseModel):
    overlaps: list[str]
