"""Shared pytest fixtures for PawPal+ tests"""

import pytest
from datetime import datetime
from pawpal_system import Owner, Pet, Task, Category, Priority, Frequency, Gender


# ============================================================
# OWNER FIXTURES
# ============================================================

@pytest.fixture
def owner():
    """Basic Owner with default settings"""
    return Owner(name="TestOwner")


@pytest.fixture
def owner_with_schedule():
    """Owner with custom work schedule (8 AM - 10 AM, 15 min breaks)"""
    return Owner(
        name="TestOwner",
        work_start_hour=8,
        work_end_hour=10,
        break_between_tasks_minutes=15
    )


@pytest.fixture
def owner_short_window():
    """Owner with short work window (1 hour: 8 AM - 9 AM)"""
    return Owner(
        name="TestOwner",
        work_start_hour=8,
        work_end_hour=9
    )


@pytest.fixture
def owner_custom_hours():
    """Owner with custom work hours (9:30 AM - 5:45 PM)"""
    return Owner(
        name="TestOwner",
        work_start_hour=9,
        work_start_minute=30,
        work_end_hour=17,
        work_end_minute=45
    )


@pytest.fixture
def owner_long_break():
    """Owner with long break duration (30 minutes)"""
    return Owner(
        name="TestOwner",
        work_start_hour=8,
        work_end_hour=10,
        break_between_tasks_minutes=30
    )


@pytest.fixture
def owner_backward_schedule():
    """Owner with invalid schedule (end before start)"""
    return Owner(
        name="TestOwner",
        work_start_hour=18,
        work_end_hour=8
    )


# ============================================================
# PET FIXTURES
# ============================================================

@pytest.fixture
def pet():
    """Basic pet (dog)"""
    return Pet(name="Max", pet_type="dog", age=3, gender=Gender.MALE)


@pytest.fixture
def pet_female():
    """Female pet"""
    return Pet(name="Whiskers", pet_type="cat", age=2, gender=Gender.FEMALE)


# ============================================================
# OWNER + PET COMBINATIONS
# ============================================================

@pytest.fixture
def owner_with_pet(owner, pet):
    """Owner with one pet already added"""
    owner.add_pet(pet)
    return owner


@pytest.fixture
def owner_with_multiple_pets(owner, pet, pet_female):
    """Owner with multiple pets"""
    owner.add_pet(pet)
    owner.add_pet(pet_female)
    return owner


@pytest.fixture
def owner_schedule_with_pet(owner_with_schedule, pet):
    """Owner with schedule and pet"""
    owner_with_schedule.add_pet(pet)
    return owner_with_schedule


# ============================================================
# TASK FIXTURES
# ============================================================

@pytest.fixture
def task_walk():
    """Basic walk task (30 min, high priority)"""
    return Task(
        name="Morning Walk",
        category=Category.EXERCISE,
        pet_id="test-pet-id",
        duration=30,
        priority=Priority.HIGH,
        frequency=Frequency.DAILY
    )


@pytest.fixture
def task_feed():
    """Feeding task (15 min, high priority)"""
    return Task(
        name="Feed",
        category=Category.FEEDING,
        pet_id="test-pet-id",
        duration=15,
        priority=Priority.HIGH,
        frequency=Frequency.DAILY
    )


@pytest.fixture
def task_play():
    """Play task (20 min, low priority)"""
    return Task(
        name="Play",
        category=Category.PLAY,
        pet_id="test-pet-id",
        duration=20,
        priority=Priority.LOW,
        frequency=Frequency.ONCE
    )


@pytest.fixture
def task_grooming():
    """Grooming task (45 min, medium priority)"""
    return Task(
        name="Grooming",
        category=Category.GROOMING,
        pet_id="test-pet-id",
        duration=45,
        priority=Priority.MEDIUM,
        frequency=Category.GROOMING
    )


@pytest.fixture
def task_medication():
    """Medication task (10 min, high priority)"""
    return Task(
        name="Medication",
        category=Category.MEDICATION,
        pet_id="test-pet-id",
        duration=10,
        priority=Priority.HIGH
    )


@pytest.fixture
def task_zero_duration():
    """Invalid task with zero duration"""
    return Task(
        name="Instant Task",
        category=Category.PLAY,
        pet_id="test-pet-id",
        duration=0
    )




@pytest.fixture
def task_very_long():
    """Task with unrealistic duration (1000 hours)"""
    return Task(
        name="Century Task",
        category=Category.PLAY,
        pet_id="test-pet-id",
        duration=60000
    )


@pytest.fixture
def task_with_nonexistent_pet():
    """Task referencing pet that doesn't exist"""
    return Task(
        name="Walk",
        category=Category.EXERCISE,
        pet_id="nonexistent-pet-12345",
        duration=30
    )


@pytest.fixture
def task_with_empty_pet_id():
    """Task with empty pet ID"""
    return Task(
        name="Walk",
        category=Category.EXERCISE,
        pet_id="",
        duration=30
    )


# ============================================================
# TASK SETS (multiple tasks)
# ============================================================

@pytest.fixture
def tasks_high_and_medium(task_walk, task_feed):
    """Set of high and medium priority tasks"""
    return [task_walk, task_feed]


@pytest.fixture
def tasks_mixed_priority(task_walk, task_feed, task_play):
    """Set of tasks with mixed priorities (high, high, low)"""
    return [task_walk, task_feed, task_play]


@pytest.fixture
def tasks_all_too_long(owner_short_window, pet):
    """Set of tasks that don't fit in short work window"""
    tasks = [
        Task(name="Task1", category=Category.PLAY, pet_id=pet.id, duration=45, priority=Priority.HIGH),
        Task(name="Task2", category=Category.PLAY, pet_id=pet.id, duration=40, priority=Priority.MEDIUM),
    ]
    return tasks
