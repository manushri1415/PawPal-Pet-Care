'''
Logic layer for PawPal+ pet care scheduling system
'''

from datetime import datetime, timedelta
from typing import List, Optional
from enum import Enum
import uuid


# ============================================================
# ENUMS FOR TYPE SAFETY
# ============================================================

class Gender(Enum):
    """Pet gender options."""
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class Priority(Enum):
    """Task priority levels."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Frequency(Enum):
    """Task recurrence patterns."""
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    AS_NEEDED = "as_needed"


class Category(Enum):
    """Task categories."""
    FEEDING = "feeding"
    EXERCISE = "exercise"
    GROOMING = "grooming"
    MEDICATION = "medication"
    ENRICHMENT = "enrichment"
    PLAY = "play"
    TRAINING = "training"
    MEDICAL = "medical"
    OTHER = "other"


# ============================================================
# CORE CLASSES
# ============================================================

class Task:
    """Represents a single pet care activity with scheduling parameters."""

    def __init__(self, name: str, category: Category, pet_id: str, duration: int,
                 priority: Priority = Priority.MEDIUM, frequency: Frequency = Frequency.ONCE,
                 notes: str = "", scheduled_time: str = "", due_date: Optional[datetime] = None):
        """
        Args:
            name: Task name (e.g., "Morning walk")
            category: Task category from Category enum
            pet_id: ID of the pet this task is for
            duration: Duration in minutes (must be >= 0)
            priority: Priority level from Priority enum
            frequency: Recurrence pattern from Frequency enum
            notes: Optional notes (e.g., medication details, food names)
            scheduled_time: Preferred time in "HH:MM" format (e.g., "08:30")
            due_date: Due date for the task (datetime object). If None, defaults to today.

        Raises:
            ValueError: If duration is negative
        """
        if duration < 0:
            raise ValueError(f"Task duration must be non-negative, got {duration}")

        self.id = str(uuid.uuid4())
        self.name = name
        self.category = category
        self.pet_id = pet_id
        self.duration = duration
        self.priority = priority
        self.frequency = frequency
        self.notes = notes
        self.scheduled_time = scheduled_time
        self.due_date = due_date if due_date else datetime.now()
        self.completed = False

    def is_recurring(self) -> bool:
        """Check if this task repeats (daily, weekly, etc.)."""
        return self.frequency != Frequency.ONCE

    def can_fit_in_time_slot(self, start_time: datetime, end_time: datetime) -> bool:
        """Check if task duration fits in the given time window."""
        available_minutes = (end_time - start_time).total_seconds() / 60
        return self.duration <= available_minutes

    def get_estimated_end_time(self, start_time: datetime) -> datetime:
        """Calculate when task would end if started at start_time."""
        return start_time + timedelta(minutes=self.duration)

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.completed = True

    def calculate_next_due_date(self) -> Optional[datetime]:
        """Calculate the due date for the next occurrence of this recurring task.

        Returns None for non-recurring tasks (ONCE, AS_NEEDED).
        Uses Python's timedelta for accurate date arithmetic.
        """
        if not self.is_recurring() or self.frequency == Frequency.AS_NEEDED:
            return None

        if self.frequency == Frequency.DAILY:
            return self.due_date + timedelta(days=1)
        elif self.frequency == Frequency.WEEKLY:
            return self.due_date + timedelta(days=7)
        elif self.frequency == Frequency.MONTHLY:
            next_month = self.due_date.replace(day=1) + timedelta(days=32)
            return next_month.replace(day=self.due_date.day)

        return None

    def create_next_occurrence(self) -> "Task":
        """Create a new Task instance for the next occurrence of this recurring task.

        Returns a new Task with the same properties but updated due_date and completed=False.
        Raises ValueError if called on a non-recurring task.
        """
        if not self.is_recurring() or self.frequency == Frequency.AS_NEEDED:
            raise ValueError(f"Cannot create next occurrence for non-recurring task: {self.frequency}")

        next_due = self.calculate_next_due_date()
        if next_due is None:
            raise ValueError(f"Could not calculate next due date for frequency: {self.frequency}")

        return Task(
            name=self.name,
            category=self.category,
            pet_id=self.pet_id,
            duration=self.duration,
            priority=self.priority,
            frequency=self.frequency,
            notes=self.notes,
            scheduled_time=self.scheduled_time,
            due_date=next_due
        )


class Pet:
    """Stores pet details and manages its associated tasks."""

    def __init__(self, name: str, pet_type: str, age: int,
                 gender: Gender = Gender.UNKNOWN, color: str = "", age_months: int = 0):
        """
        Args:
            name: Pet name
            pet_type: Type of pet (e.g., "dog", "cat")
            age: Age in years
            gender: Pet gender from Gender enum
            color: Pet color/appearance
            age_months: Additional months (0-11)
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = pet_type
        self.age = age
        self.age_months = age_months
        self.gender = gender
        self.color = color
        self.tasks: List[Task] = []

    def add_task(self, task: Task) -> None:
        """Add a task to this pet."""
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> None:
        """Remove a task by ID."""
        self.tasks = [t for t in self.tasks if t.id != task_id]

    def get_tasks(self) -> List[Task]:
        """Return all tasks for this pet."""
        return self.tasks

    def get_tasks_for_day(self, date: datetime) -> List[Task]:
        """Return recurring and one-time tasks relevant for a specific date."""
        # TODO: Implement date-based filtering (check frequency and scheduling)
        return self.tasks


class Owner:
    """Manages multiple pets and provides unified access to their tasks."""

    def __init__(self, name: str, email: str = "", phone_number: str = "", available_hours_per_day: float = 8.0,
                 work_start_hour: int = 8, work_start_minute: int = 0,
                 work_end_hour: int = 18, work_end_minute: int = 0,
                 break_between_tasks_minutes: int = 15):
        """
        Args:
            name: Owner name
            email: Owner email
            phone_number: Owner phone number
            available_hours_per_day: Hours owner can dedicate to pet care per day (must be > 0)
            work_start_hour: Hour work day starts (0-23)
            work_start_minute: Minute work day starts (0-59)
            work_end_hour: Hour work day ends (0-23)
            work_end_minute: Minute work day ends (0-59)
            break_between_tasks_minutes: Break duration between tasks in minutes (must be >= 0)

        Raises:
            ValueError: If hours/minutes are out of valid range or available_hours_per_day <= 0
        """
        if available_hours_per_day <= 0:
            raise ValueError(f"available_hours_per_day must be positive, got {available_hours_per_day}")
        if not (0 <= work_start_hour <= 23):
            raise ValueError(f"work_start_hour must be 0-23, got {work_start_hour}")
        if not (0 <= work_end_hour <= 23):
            raise ValueError(f"work_end_hour must be 0-23, got {work_end_hour}")
        if not (0 <= work_start_minute <= 59):
            raise ValueError(f"work_start_minute must be 0-59, got {work_start_minute}")
        if not (0 <= work_end_minute <= 59):
            raise ValueError(f"work_end_minute must be 0-59, got {work_end_minute}")
        if break_between_tasks_minutes < 0:
            raise ValueError(f"break_between_tasks_minutes must be non-negative, got {break_between_tasks_minutes}")

        self.id = str(uuid.uuid4())
        self.name = name
        self.email = email
        self.phone_number = phone_number
        self.available_hours_per_day = available_hours_per_day
        self.work_start_hour = work_start_hour
        self.work_start_minute = work_start_minute
        self.work_end_hour = work_end_hour
        self.work_end_minute = work_end_minute
        self.break_between_tasks_minutes = break_between_tasks_minutes
        self.pets: List[Pet] = []
        self.tasks: List[Task] = []  # Owner-level tasks (if any)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner."""
        self.pets.append(pet)

    def remove_pet(self, pet_id: str) -> None:
        """Remove a pet by ID."""
        self.pets = [p for p in self.pets if p.id != pet_id]

    def get_pets(self) -> List[Pet]:
        """Return all pets owned by this owner."""
        return self.pets

    def add_task(self, task: Task) -> None:
        """Add a task (can be pet-specific or owner-level).

        Raises:
            ValueError: If task references a non-existent pet ID
        """
        if task.pet_id:
            for pet in self.pets:
                if pet.id == task.pet_id:
                    pet.add_task(task)
                    return
            raise ValueError(f"Pet with ID '{task.pet_id}' does not exist")
        else:
            self.tasks.append(task)

    def edit_task(self, task_id: str, updates: dict) -> Optional[Task]:
        """Edit a task by ID with the provided updates."""
        # Search all pets first
        for pet in self.pets:
            for task in pet.tasks:
                if task.id == task_id:
                    for key, value in updates.items():
                        if hasattr(task, key):
                            setattr(task, key, value)
                    return task

        # Search owner-level tasks
        for task in self.tasks:
            if task.id == task_id:
                for key, value in updates.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                return task

        return None

    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID."""
        # Search all pets first
        for pet in self.pets:
            if any(t.id == task_id for t in pet.tasks):
                pet.remove_task(task_id)
                return True

        # Search owner-level tasks
        if any(t.id == task_id for t in self.tasks):
            self.tasks = [t for t in self.tasks if t.id != task_id]
            return True

        return False

    def mark_task_complete(self, task_id: str) -> bool:
        """Mark a task as complete and create next occurrence if it's recurring.

        For recurring tasks (DAILY, WEEKLY, MONTHLY), automatically creates a new
        instance with the next due date.

        Args:
            task_id: ID of the task to complete

        Returns:
            True if task was found and marked complete, False otherwise
        """
        target_task = None
        pet_container = None

        # Search all pets for the task
        for pet in self.pets:
            for task in pet.tasks:
                if task.id == task_id:
                    target_task = task
                    pet_container = pet
                    break
            if target_task:
                break

        # Search owner-level tasks
        if not target_task:
            for task in self.tasks:
                if task.id == task_id:
                    target_task = task
                    break

        if not target_task:
            return False

        target_task.mark_complete()

        # If recurring, create the next occurrence
        if target_task.is_recurring() and target_task.frequency != Frequency.AS_NEEDED:
            next_task = target_task.create_next_occurrence()
            if pet_container:
                pet_container.add_task(next_task)
            else:
                self.tasks.append(next_task)

        return True

    def get_tasks(self) -> List[Task]:
        """Return owner-level tasks only."""
        return self.tasks

    def get_available_hours(self) -> float:
        """Return available hours per day."""
        return self.available_hours_per_day

    def get_work_day_start_time(self, date: datetime) -> datetime:
        """Get the work day start time for a given date.

        Raises:
            ValueError: If hours/minutes are invalid for datetime construction
        """
        try:
            return date.replace(hour=self.work_start_hour, minute=self.work_start_minute, second=0, microsecond=0)
        except ValueError as e:
            raise ValueError(f"Invalid work start time: hour={self.work_start_hour}, minute={self.work_start_minute}") from e

    def get_work_day_end_time(self, date: datetime) -> datetime:
        """Get the work day end time for a given date.

        For overnight schedules (end_hour < start_hour), adds one day to end time.

        Raises:
            ValueError: If hours/minutes are invalid for datetime construction
        """
        try:
            end = date.replace(hour=self.work_end_hour, minute=self.work_end_minute, second=0, microsecond=0)
            if self.work_end_hour < self.work_start_hour:
                end = end + timedelta(days=1)
            return end
        except ValueError as e:
            raise ValueError(f"Invalid work end time: hour={self.work_end_hour}, minute={self.work_end_minute}") from e

    def get_all_tasks_across_pets(self) -> List[Task]:
        """Return ALL tasks across all pets (the aggregator method)."""
        all_tasks = []
        for pet in self.pets:
            all_tasks.extend(pet.get_tasks())
        all_tasks.extend(self.tasks)  # Include owner-level tasks
        return all_tasks


class Scheduler:
    """The 'brain' that retrieves, organizes, and manages tasks across pets."""

    def __init__(self, owner: Owner):
        """
        Args:
            owner: The Owner instance whose pets and tasks to schedule
        """
        self.owner = owner

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks across all owner's pets."""
        return self.owner.get_all_tasks_across_pets()

    def get_tasks_for_date(self, date: datetime) -> List[Task]:
        """Get tasks relevant for a specific date based on frequency.

        Returns tasks that should run on the given date:
        - ONCE: always included
        - DAILY: always included
        - WEEKLY: included if day of week matches (using day_of_week attribute)
        - MONTHLY: included if day of month matches (using day_of_month attribute)
        - AS_NEEDED: always included
        """
        all_tasks = self.get_all_tasks()
        relevant_tasks = []

        for task in all_tasks:
            if task.frequency == Frequency.ONCE or task.frequency == Frequency.DAILY or task.frequency == Frequency.AS_NEEDED:
                relevant_tasks.append(task)
            elif task.frequency == Frequency.WEEKLY:
                if hasattr(task, 'day_of_week') and task.day_of_week == date.weekday():
                    relevant_tasks.append(task)
            elif task.frequency == Frequency.MONTHLY:
                if hasattr(task, 'day_of_month') and task.day_of_month == date.day:
                    relevant_tasks.append(task)
            else:
                relevant_tasks.append(task)

        return relevant_tasks

    def sort_by_priority(self, tasks: List[Task]) -> List[Task]:
        """Sort tasks by priority level (high > medium > low).

        Higher priority tasks are placed first, making this suitable for scheduling
        critical tasks (medications, high-priority care) before lower-priority ones.

        Args:
            tasks: List of Task objects to sort

        Returns:
            Sorted list with HIGH priority first, then MEDIUM, then LOW
        """
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        return sorted(tasks, key=lambda t: priority_order.get(t.priority, 3))

    def sort_by_duration(self, tasks: List[Task]) -> List[Task]:
        """Sort tasks by duration in ascending order (shortest first).

        Quick tasks appear at the front of the schedule, which is useful for
        fitting more activities into limited time slots and maintaining momentum.

        Args:
            tasks: List of Task objects to sort

        Returns:
            Sorted list with shortest duration tasks first
        """
        return sorted(tasks, key=lambda t: t.duration)

    def sort_by_time(self, tasks: List[Task]) -> List[Task]:
        """Sort tasks by scheduled_time in HH:MM format (earliest first).

        Tasks are ordered by their preferred start time. Tasks without a scheduled_time
        are pushed to the end, allowing flexible scheduling around fixed-time activities.

        Args:
            tasks: List of Task objects to sort

        Returns:
            Sorted list with earliest scheduled times first, unscheduled tasks last
        """
        def time_key(task):
            if not task.scheduled_time:
                return "23:59"
            return task.scheduled_time
        return sorted(tasks, key=time_key)

    def can_fit_all_tasks(self, tasks: List[Task], available_minutes: float) -> bool:
        """Check if all tasks fit in available time."""
        total_duration = sum(t.duration for t in tasks)
        return total_duration <= available_minutes

    def filter_by_pet(self, tasks: List[Task], pet_name: str) -> List[Task]:
        """Filter tasks to return only those belonging to a specific pet.

        Performs a case-insensitive name lookup to find the matching pet, then
        returns all tasks associated with that pet's ID.

        Args:
            tasks: List of Task objects to filter
            pet_name: Name of the pet (case-insensitive)

        Returns:
            List of tasks for the specified pet, or empty list if pet not found
        """
        matching_pet = None
        for pet in self.owner.get_pets():
            if pet.name.lower() == pet_name.lower():
                matching_pet = pet
                break
        if not matching_pet:
            return []
        return [t for t in tasks if t.pet_id == matching_pet.id]

    def filter_by_status(self, tasks: List[Task], completed: bool) -> List[Task]:
        """Filter tasks by completion status.

        Args:
            tasks: List of tasks to filter
            completed: True for completed tasks, False for incomplete tasks
        """
        return [t for t in tasks if t.completed == completed]

    def mark_task_complete(self, task_id: str) -> bool:
        """Mark a task as complete and auto-create next occurrence if recurring.

        Convenience wrapper around Owner.mark_task_complete().

        Args:
            task_id: ID of the task to complete

        Returns:
            True if task was found and marked complete, False otherwise
        """
        return self.owner.mark_task_complete(task_id)

    def detect_conflicts(self, schedule: List[tuple]) -> List[str]:
        """
        Detect time conflicts in a schedule (lightweight, non-crashing approach).

        Checks if any tasks overlap in time. Works for same-pet and different-pet scenarios.

        Args:
            schedule: List of tuples (task, start_time, end_time) from generate_daily_schedule

        Returns:
            List of warning messages describing conflicts. Empty list if no conflicts.
        """
        pet_name_map = {pet.id: pet.name for pet in self.owner.get_pets()}
        warnings = []

        for i, (task1, start1, end1) in enumerate(schedule):
            for task2, start2, end2 in schedule[i + 1:]:
                if start1 < end2 and start2 < end1:
                    pet1_name = pet_name_map.get(task1.pet_id, "Unknown")
                    pet2_name = pet_name_map.get(task2.pet_id, "Unknown")

                    warning = (f"[CONFLICT] '{task1.name}' ({pet1_name}) [{start1.strftime('%H:%M')}-{end1.strftime('%H:%M')}] "
                              f"overlaps with '{task2.name}' ({pet2_name}) [{start2.strftime('%H:%M')}-{end2.strftime('%H:%M')}]")
                    warnings.append(warning)

        return warnings

    def generate_daily_schedule(self, date: datetime = None) -> List[tuple]:
        """
        Generate a daily schedule with time slots for the given date (or today).

        Returns a list of tuples: (task, start_time, end_time)
        Each tuple represents when a task should be scheduled.

        Raises:
            ValueError: If work hours are invalid (e.g., out of 24-hour range)
        """
        if date is None:
            date = datetime.now()

        tasks = self.get_tasks_for_date(date)
        work_start = self.owner.get_work_day_start_time(date)
        work_end = self.owner.get_work_day_end_time(date)
        break_duration = timedelta(minutes=self.owner.break_between_tasks_minutes)

        sorted_tasks = self.sort_by_priority(tasks)

        scheduled = []
        current_time = work_start

        for task in sorted_tasks:
            task_duration = timedelta(minutes=task.duration)
            task_end = current_time + task_duration

            if task_end <= work_end:
                scheduled.append((task, current_time, task_end))
                current_time = task_end + break_duration

                if current_time > work_end:
                    current_time = work_end

        return scheduled
