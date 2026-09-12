"""Domain-object rehydration + persistence glue for the scheduler API.

Routers never touch pawpal_system.py or api/storage.py directly — they go
through SchedulerService, which is the one place that (a) turns SQL rows
into real Owner/Pet/Task objects when a domain method needs the graph,
(b) calls that one domain method, and (c) persists back only the rows it's
documented to touch. This is what fixes the old Streamlit bugs (pet-delete
bypassing Owner.remove_pet, task-uncomplete bypassing any domain method, the
ad hoc overlap check duplicated in app.py) for free — see MIGRATION_PLAN.md §7.

Rehydrating the full owner graph (all pets + all tasks) on every mutating
call is deliberately simple rather than optimized: this is a single-user,
low-volume app, so the cost is negligible and it keeps every domain method
(which expects to walk owner.pets / owner.tasks) usable exactly as written.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Callable, Optional

from pawpal_system import Category, Frequency, Gender, Owner, Pet, Priority, Scheduler, Task

from api.schemas.scheduler import (
    OverlapsResponse,
    OwnerRead,
    OwnerUpdate,
    PetCreate,
    PetRead,
    PetUpdate,
    ScheduledItem,
    ScheduleGenerateResponse,
    TaskCompleteResponse,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from api.storage import SchedulerStorage


class PetHasHealthRecordsError(Exception):
    """Raised by delete_pet when deleting would orphan existing health records.

    Carries the count so the router can render "N health record(s) exist;
    pass ?force=true" (see MIGRATION_PLAN.md §2).
    """

    def __init__(self, count: int):
        self.count = count
        super().__init__(f"{count} health record(s) exist for this pet")


class SchedulerService:
    def __init__(
        self,
        storage: SchedulerStorage,
        health_record_counter: Optional[Callable[[str], int]] = None,
    ):
        """
        Args:
            storage: SchedulerStorage for owners/pets/tasks.
            health_record_counter: optional callable(pet_id) -> int, used only
                by delete_pet to check for orphaned health records. Injected
                rather than importing pawpal_ai.storage directly so this
                service (and its tests) don't need a health Storage at all
                when the check doesn't matter.
        """
        self.storage = storage
        self._health_record_counter = health_record_counter

    # -- row/object -> schema helpers ---------------------------------------

    @staticmethod
    def _owner_row_to_schema(row: sqlite3.Row) -> OwnerRead:
        return OwnerRead(
            owner_id=row["owner_id"],
            name=row["name"],
            email=row["email"] or "",
            phone_number=row["phone_number"] or "",
            available_hours_per_day=row["available_hours_per_day"],
            work_start_hour=row["work_start_hour"],
            work_start_minute=row["work_start_minute"],
            work_end_hour=row["work_end_hour"],
            work_end_minute=row["work_end_minute"],
            break_between_tasks_minutes=row["break_between_tasks_minutes"],
        )

    @staticmethod
    def _pet_row_to_schema(row: sqlite3.Row) -> PetRead:
        return PetRead(
            pet_id=row["pet_id"],
            owner_id=row["owner_id"],
            name=row["name"],
            pet_type=row["pet_type"],
            age=row["age"],
            age_months=row["age_months"],
            gender=Gender(row["gender"]),
            color=row["color"] or "",
        )

    @staticmethod
    def _task_row_to_schema(row: sqlite3.Row) -> TaskRead:
        return TaskRead(
            task_id=row["task_id"],
            owner_id=row["owner_id"],
            pet_id=row["pet_id"],
            name=row["name"],
            category=Category(row["category"]),
            duration=row["duration"],
            priority=Priority(row["priority"]),
            frequency=Frequency(row["frequency"]),
            notes=row["notes"] or "",
            scheduled_time=row["scheduled_time"] or "",
            due_date=datetime.fromisoformat(row["due_date"]),
            end_date=datetime.fromisoformat(row["end_date"]) if row["end_date"] else None,
            completed=bool(row["completed"]),
        )

    @staticmethod
    def _task_to_schema(task: Task, owner_id: str) -> TaskRead:
        """Same as _task_row_to_schema but from a rehydrated Task object."""
        return TaskRead(
            task_id=task.id,
            owner_id=owner_id,
            pet_id=task.pet_id or None,
            name=task.name,
            category=task.category,
            duration=task.duration,
            priority=task.priority,
            frequency=task.frequency,
            notes=task.notes,
            scheduled_time=task.scheduled_time,
            due_date=task.due_date,
            end_date=task.end_date,
            completed=task.completed,
        )

    @staticmethod
    def _row_to_task_obj(row: sqlite3.Row) -> Task:
        """Rehydrate one task row into a real pawpal_system.Task."""
        task = Task(
            name=row["name"],
            category=Category(row["category"]),
            pet_id=row["pet_id"] or "",
            duration=row["duration"],
            priority=Priority(row["priority"]),
            frequency=Frequency(row["frequency"]),
            notes=row["notes"] or "",
            scheduled_time=row["scheduled_time"] or "",
            due_date=datetime.fromisoformat(row["due_date"]),
            end_date=datetime.fromisoformat(row["end_date"]) if row["end_date"] else None,
        )
        task.id = row["task_id"]
        task.completed = bool(row["completed"])
        return task

    def _rehydrate_owner(self) -> Owner:
        """Build the full in-memory Owner graph (all pets + all tasks)."""
        orow = self.storage.get_or_create_owner()
        owner = Owner(
            name=orow["name"],
            email=orow["email"] or "",
            phone_number=orow["phone_number"] or "",
            available_hours_per_day=orow["available_hours_per_day"],
            work_start_hour=orow["work_start_hour"],
            work_start_minute=orow["work_start_minute"],
            work_end_hour=orow["work_end_hour"],
            work_end_minute=orow["work_end_minute"],
            break_between_tasks_minutes=orow["break_between_tasks_minutes"],
        )
        owner.id = orow["owner_id"]

        pets_by_id: dict[str, Pet] = {}
        for prow in self.storage.list_pets(orow["owner_id"]):
            pet = Pet(
                name=prow["name"],
                pet_type=prow["pet_type"],
                age=prow["age"],
                gender=Gender(prow["gender"]),
                color=prow["color"] or "",
                age_months=prow["age_months"],
            )
            pet.id = prow["pet_id"]
            owner.pets.append(pet)
            pets_by_id[pet.id] = pet

        for trow in self.storage.list_tasks(orow["owner_id"]):
            task = self._row_to_task_obj(trow)
            if task.pet_id and task.pet_id in pets_by_id:
                pets_by_id[task.pet_id].tasks.append(task)
            else:
                owner.tasks.append(task)

        return owner

    @staticmethod
    def _find_task_container(owner: Owner, task_id: str):
        """Locate the list (a pet's .tasks, or owner.tasks) holding task_id."""
        for pet in owner.pets:
            for t in pet.tasks:
                if t.id == task_id:
                    return pet.tasks, t
        for t in owner.tasks:
            if t.id == task_id:
                return owner.tasks, t
        return None, None

    # -- owner ----------------------------------------------------------------

    def get_owner(self) -> OwnerRead:
        return self._owner_row_to_schema(self.storage.get_or_create_owner())

    def update_owner(self, patch: OwnerUpdate) -> OwnerRead:
        current = self.storage.get_or_create_owner()
        merged = {
            "name": current["name"],
            "email": current["email"] or "",
            "phone_number": current["phone_number"] or "",
            "available_hours_per_day": current["available_hours_per_day"],
            "work_start_hour": current["work_start_hour"],
            "work_start_minute": current["work_start_minute"],
            "work_end_hour": current["work_end_hour"],
            "work_end_minute": current["work_end_minute"],
            "break_between_tasks_minutes": current["break_between_tasks_minutes"],
        }
        merged.update(patch.model_dump(exclude_unset=True))
        # Reuse Owner's own constructor validation (hour/minute ranges,
        # available_hours_per_day > 0) instead of duplicating those checks --
        # raises ValueError on anything invalid, which the router turns into 422.
        Owner(**merged)
        row = self.storage.update_owner(**merged)
        return self._owner_row_to_schema(row)

    # -- pets -------------------------------------------------------------------

    def list_pets(self) -> list[PetRead]:
        owner = self.storage.get_or_create_owner()
        return [self._pet_row_to_schema(r) for r in self.storage.list_pets(owner["owner_id"])]

    def create_pet(self, data: PetCreate) -> PetRead:
        owner = self.storage.get_or_create_owner()
        # Pet() constructor validates age/age_months (raises ValueError on
        # invalid combos) -- the one source of truth for that rule.
        pet = Pet(
            name=data.name,
            pet_type=data.pet_type,
            age=data.age,
            gender=data.gender,
            color=data.color,
            age_months=data.age_months,
        )
        row = self.storage.create_pet(pet, owner["owner_id"])
        return self._pet_row_to_schema(row)

    def get_pet(self, pet_id: str) -> Optional[PetRead]:
        row = self.storage.get_pet(pet_id)
        return self._pet_row_to_schema(row) if row else None

    def update_pet(self, pet_id: str, patch: PetUpdate) -> Optional[PetRead]:
        current = self.storage.get_pet(pet_id)
        if current is None:
            return None
        merged = {
            "name": current["name"],
            "pet_type": current["pet_type"],
            "age": current["age"],
            "age_months": current["age_months"],
            "gender": Gender(current["gender"]),
            "color": current["color"] or "",
        }
        merged.update(patch.model_dump(exclude_unset=True))
        # Re-validate through the constructor (age/age_months rules), same
        # reasoning as update_owner.
        Pet(
            name=merged["name"],
            pet_type=merged["pet_type"],
            age=merged["age"],
            gender=merged["gender"],
            color=merged["color"],
            age_months=merged["age_months"],
        )
        row = self.storage.update_pet(
            pet_id,
            name=merged["name"],
            pet_type=merged["pet_type"],
            age=merged["age"],
            age_months=merged["age_months"],
            gender=merged["gender"].value,
            color=merged["color"],
        )
        return self._pet_row_to_schema(row)

    def delete_pet(self, pet_id: str, force: bool = False) -> Optional[bool]:
        """Delete a pet. Returns None if not found, True once deleted.

        Raises PetHasHealthRecordsError if health records exist and force is
        False (see MIGRATION_PLAN.md §2 — default to 409, don't silently
        orphan them).
        """
        if self.storage.get_pet(pet_id) is None:
            return None
        if not force and self._health_record_counter is not None:
            count = self._health_record_counter(pet_id)
            if count:
                raise PetHasHealthRecordsError(count)
        # Go through the real domain method (owner.remove_pet) rather than a
        # raw DELETE, per the bug fix in MIGRATION_PLAN.md §7 -- pet delete
        # bypassing Owner.remove_pet was one of the bugs this migration fixes.
        owner = self._rehydrate_owner()
        owner.remove_pet(pet_id)
        self.storage.delete_pet(pet_id)
        return True

    # -- tasks ------------------------------------------------------------------

    def list_tasks(
        self, pet_id: Optional[str] = None, status: str = "open", sort: Optional[str] = None
    ) -> list[TaskRead]:
        owner = self._rehydrate_owner()
        tasks = owner.get_all_tasks_across_pets()
        if pet_id is not None:
            tasks = [t for t in tasks if t.pet_id == pet_id]
        if status == "open":
            tasks = [t for t in tasks if not t.completed]
        elif status == "completed":
            tasks = [t for t in tasks if t.completed]
        # status == "all": no filtering

        scheduler = Scheduler(owner)
        if sort == "priority":
            tasks = scheduler.sort_by_priority(tasks)
        elif sort == "time":
            tasks = scheduler.sort_by_time(tasks)
        elif sort == "duration":
            tasks = scheduler.sort_by_duration(tasks)

        return [self._task_to_schema(t, owner.id) for t in tasks]

    def create_task(self, data: TaskCreate) -> TaskRead:
        owner = self._rehydrate_owner()
        task = Task(
            name=data.name,
            category=data.category,
            pet_id=data.pet_id or "",
            duration=data.duration,
            priority=data.priority,
            frequency=data.frequency,
            notes=data.notes,
            scheduled_time=data.scheduled_time,
            due_date=data.due_date,
            end_date=data.end_date,
        )
        owner.add_task(task)  # raises ValueError if pet_id doesn't exist
        row = self.storage.create_task(task, owner.id)
        return self._task_row_to_schema(row)

    def get_task(self, task_id: str) -> Optional[TaskRead]:
        row = self.storage.get_task(task_id)
        return self._task_row_to_schema(row) if row else None

    def update_task(self, task_id: str, patch: TaskUpdate) -> Optional[TaskRead]:
        current = self.storage.get_task(task_id)
        if current is None:
            return None
        current_task = self._row_to_task_obj(current)
        merged = {
            "name": current_task.name,
            "category": current_task.category,
            "pet_id": current_task.pet_id,
            "duration": current_task.duration,
            "priority": current_task.priority,
            "frequency": current_task.frequency,
            "notes": current_task.notes,
            "scheduled_time": current_task.scheduled_time,
            "due_date": current_task.due_date,
            "end_date": current_task.end_date,
        }
        merged.update(patch.model_dump(exclude_unset=True))
        if merged["pet_id"] and self.storage.get_pet(merged["pet_id"]) is None:
            raise ValueError(f"Pet with ID '{merged['pet_id']}' does not exist")
        # Re-validate through the constructor (duration >= 0), same reasoning
        # as update_owner/update_pet.
        Task(
            name=merged["name"],
            category=merged["category"],
            pet_id=merged["pet_id"] or "",
            duration=merged["duration"],
            priority=merged["priority"],
            frequency=merged["frequency"],
            notes=merged["notes"],
            scheduled_time=merged["scheduled_time"],
            due_date=merged["due_date"],
            end_date=merged["end_date"],
        )
        row = self.storage.update_task(
            task_id,
            name=merged["name"],
            category=merged["category"].value,
            pet_id=merged["pet_id"] or None,
            duration=merged["duration"],
            priority=merged["priority"].value,
            frequency=merged["frequency"].value,
            notes=merged["notes"],
            scheduled_time=merged["scheduled_time"],
            due_date=merged["due_date"].isoformat(),
            end_date=merged["end_date"].isoformat() if merged["end_date"] else None,
        )
        return self._task_row_to_schema(row)

    def delete_task(self, task_id: str) -> bool:
        owner = self._rehydrate_owner()
        found = owner.delete_task(task_id)
        if not found:
            return False
        self.storage.delete_task(task_id)
        return True

    def complete_task(self, task_id: str) -> Optional[TaskCompleteResponse]:
        owner = self._rehydrate_owner()
        container, target = self._find_task_container(owner, task_id)
        if target is None:
            return None

        before_len = len(container)
        owner.mark_task_complete(task_id)
        self.storage.update_task(task_id, completed=1)

        next_occurrence = None
        if len(container) > before_len:
            next_task = container[-1]
            next_row = self.storage.create_task(next_task, owner.id)
            next_occurrence = self._task_row_to_schema(next_row)

        updated_row = self.storage.get_task(task_id)
        return TaskCompleteResponse(
            task=self._task_row_to_schema(updated_row), next_occurrence=next_occurrence
        )

    def uncomplete_task(self, task_id: str) -> Optional[TaskRead]:
        owner = self._rehydrate_owner()
        found = owner.uncomplete_task(task_id)
        if not found:
            return None
        self.storage.update_task(task_id, completed=0)
        return self._task_row_to_schema(self.storage.get_task(task_id))

    def get_overlaps(self) -> OverlapsResponse:
        owner = self._rehydrate_owner()
        warnings = Scheduler(owner).detect_time_overlaps(owner.get_all_tasks_across_pets())
        return OverlapsResponse(overlaps=warnings)

    # -- schedule -----------------------------------------------------------------

    def generate_schedule(self, date: Optional[datetime] = None) -> ScheduleGenerateResponse:
        owner = self._rehydrate_owner()
        scheduler = Scheduler(owner)
        scheduled = scheduler.generate_daily_schedule(date)
        conflicts = scheduler.detect_conflicts(scheduled)
        items = [
            ScheduledItem(task=self._task_to_schema(task, owner.id), start=start, end=end)
            for task, start, end in scheduled
        ]
        return ScheduleGenerateResponse(schedule=items, conflicts=conflicts)
