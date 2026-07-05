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
                 priority: Priority = Priority.MEDIUM, frequency: Frequency = Frequency.ONCE):
        """
        Args:
            name: Task name (e.g., "Morning walk")
            category: Task category from Category enum
            pet_id: ID of the pet this task is for
            duration: Duration in minutes
            priority: Priority level from Priority enum
            frequency: Recurrence pattern from Frequency enum
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.category = category
        self.pet_id = pet_id
        self.duration = duration
        self.priority = priority
        self.frequency = frequency
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


class Pet:
    """Stores pet details and manages its associated tasks."""

    def __init__(self, name: str, pet_type: str, age: int,
                 gender: Gender = Gender.UNKNOWN, color: str = ""):
        """
        Args:
            name: Pet name
            pet_type: Type of pet (e.g., "dog", "cat")
            age: Age in years
            gender: Pet gender from Gender enum
            color: Pet color/appearance
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = pet_type
        self.age = age
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

    def __init__(self, name: str, email: str, phone_number: str = "", available_hours_per_day: float = 8.0):
        """
        Args:
            name: Owner name
            email: Owner email
            phone_number: Owner phone number
            available_hours_per_day: Hours owner can dedicate to pet care per day
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.email = email
        self.phone_number = phone_number
        self.available_hours_per_day = available_hours_per_day
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
        """Add a task (can be pet-specific or owner-level)."""
        # If task has a pet_id, add it to that pet; otherwise add to owner level
        if task.pet_id:
            for pet in self.pets:
                if pet.id == task.pet_id:
                    pet.add_task(task)
                    return
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

    def get_tasks(self) -> List[Task]:
        """Return owner-level tasks only."""
        return self.tasks

    def get_available_hours(self) -> float:
        """Return available hours per day."""
        return self.available_hours_per_day

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
        """Get tasks relevant for a specific date."""
        # TODO: Implement date filtering logic
        return self.get_all_tasks()

    def sort_by_priority(self, tasks: List[Task]) -> List[Task]:
        """Sort tasks by priority (high > medium > low)."""
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        return sorted(tasks, key=lambda t: priority_order.get(t.priority, 3))

    def sort_by_duration(self, tasks: List[Task]) -> List[Task]:
        """Sort tasks by duration (shortest first)."""
        return sorted(tasks, key=lambda t: t.duration)

    def can_fit_all_tasks(self, tasks: List[Task], available_minutes: float) -> bool:
        """Check if all tasks fit in available time."""
        total_duration = sum(t.duration for t in tasks)
        return total_duration <= available_minutes

    def generate_daily_schedule(self, date: datetime = None) -> List[Task]:
        """
        Generate a daily schedule for the given date (or today).

        TODO: Implement scheduling logic:
        - Retrieve tasks for the date
        - Sort by priority
        - Fit as many as possible within available hours
        - Return ordered list of scheduled tasks
        """
        if date is None:
            date = datetime.now()

        tasks = self.get_tasks_for_date(date)
        available_minutes = self.owner.get_available_hours() * 60

        # Sort by priority first
        sorted_tasks = self.sort_by_priority(tasks)

        # TODO: Fit tasks intelligently into available time
        scheduled = []
        time_used = 0
        for task in sorted_tasks:
            if time_used + task.duration <= available_minutes:
                scheduled.append(task)
                time_used += task.duration

        return scheduled
