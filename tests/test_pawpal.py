"""Tests for PawPal+ system"""

from datetime import datetime, timedelta
from pawpal_system import Task, Pet, Category, Priority, Frequency, Gender, Owner, Scheduler


class TestTaskCompletion:
    """Tests for Task.mark_complete() functionality"""

    def test_mark_complete_changes_status(self, task_walk):
        """Verify that calling mark_complete() changes the task's completed status from False to True"""
        # Initial state should be not completed
        assert task_walk.completed is False

        # Mark the task as complete
        task_walk.mark_complete()

        # Status should now be True
        assert task_walk.completed is True


class TestTaskAddition:
    """Tests for adding tasks to pets"""

    def test_adding_task_to_pet_increases_task_count(self, pet, task_walk, task_feed):
        """Verify that adding a task to a Pet increases that pet's task count"""
        # Initial task count should be 0
        assert len(pet.get_tasks()) == 0

        # Update task to use this pet
        task_walk.pet_id = pet.id
        pet.add_task(task_walk)

        # Task count should now be 1
        assert len(pet.get_tasks()) == 1

        # Add another task
        task_feed.pet_id = pet.id
        pet.add_task(task_feed)

        # Task count should now be 2
        assert len(pet.get_tasks()) == 2


class TestOwnerWorkSchedule:
    """Tests for Owner work schedule configuration"""

    def test_owner_default_work_hours(self, owner):
        """Verify Owner initializes with default work hours (8 AM - 6 PM)"""
        assert owner.work_start_hour == 8
        assert owner.work_start_minute == 0
        assert owner.work_end_hour == 18
        assert owner.work_end_minute == 0

    def test_owner_custom_work_hours(self, owner_custom_hours):
        """Verify Owner can be initialized with custom work hours"""
        assert owner_custom_hours.work_start_hour == 9
        assert owner_custom_hours.work_start_minute == 30
        assert owner_custom_hours.work_end_hour == 17
        assert owner_custom_hours.work_end_minute == 45

    def test_owner_break_between_tasks(self, owner_long_break):
        """Verify Owner can set break duration between tasks"""
        assert owner_long_break.break_between_tasks_minutes == 30

    def test_get_work_day_start_time(self, owner_custom_hours):
        """Verify get_work_day_start_time returns correct datetime"""
        test_date = datetime(2026, 7, 4, 10, 0, 0)
        start_time = owner_custom_hours.get_work_day_start_time(test_date)

        assert start_time.hour == 9
        assert start_time.minute == 30
        assert start_time.day == 4
        assert start_time.month == 7
        assert start_time.year == 2026

    def test_get_work_day_end_time(self, owner_custom_hours):
        """Verify get_work_day_end_time returns correct datetime"""
        test_date = datetime(2026, 7, 4, 10, 0, 0)
        end_time = owner_custom_hours.get_work_day_end_time(test_date)

        assert end_time.hour == 17
        assert end_time.minute == 45
        assert end_time.day == 4


class TestSchedulerWithTimeSlots:
    """Tests for Scheduler generating schedules with time slots and breaks"""

    def test_schedule_returns_tuples_with_times(self, owner_with_schedule, pet, task_walk):
        """Verify generate_daily_schedule returns tuples of (task, start_time, end_time)"""
        owner_with_schedule.add_pet(pet)
        task_walk.pet_id = pet.id
        owner_with_schedule.add_task(task_walk)

        scheduler = Scheduler(owner_with_schedule)
        scheduled = scheduler.generate_daily_schedule(datetime(2026, 7, 4))

        assert len(scheduled) == 1
        task_item, start_time, end_time = scheduled[0]
        assert task_item.name == "Morning Walk"
        assert isinstance(start_time, datetime)
        assert isinstance(end_time, datetime)

    def test_schedule_respects_work_hours(self, owner_short_window, pet):
        """Verify tasks scheduled only within work hours"""
        owner_short_window.add_pet(pet)

        # Task that's 61 minutes - won't fit in 1 hour window
        task = Task(
            name="Long Task",
            category=Category.EXERCISE,
            pet_id=pet.id,
            duration=61,
            priority=Priority.HIGH
        )
        owner_short_window.add_task(task)

        scheduler = Scheduler(owner_short_window)
        scheduled = scheduler.generate_daily_schedule(datetime(2026, 7, 4))

        # Task should not be scheduled
        assert len(scheduled) == 0

    def test_schedule_includes_break_time(self, owner_with_schedule, pet):
        """Verify breaks are added between consecutive tasks"""
        owner_with_schedule.add_pet(pet)

        # Two 20-minute tasks
        task1 = Task(
            name="Walk",
            category=Category.EXERCISE,
            pet_id=pet.id,
            duration=20,
            priority=Priority.HIGH
        )
        task2 = Task(
            name="Feed",
            category=Category.FEEDING,
            pet_id=pet.id,
            duration=20,
            priority=Priority.HIGH
        )
        owner_with_schedule.add_task(task1)
        owner_with_schedule.add_task(task2)

        scheduler = Scheduler(owner_with_schedule)
        scheduled = scheduler.generate_daily_schedule(datetime(2026, 7, 4))

        # Both tasks should fit: 20 + 15 (break) + 20 = 55 minutes in 120 minute window
        assert len(scheduled) == 2

        _, _, end1 = scheduled[0]
        _, start2, _ = scheduled[1]

        # Second task should start 15 minutes after first task ends
        expected_start2 = end1 + timedelta(minutes=15)
        assert start2 == expected_start2

    def test_schedule_respects_priority(self, owner_with_schedule, pet, task_walk, task_feed, task_play):
        """Verify tasks are scheduled in priority order (high > medium > low)"""
        owner_no_break = Owner(name="TestOwner", work_start_hour=8, work_end_hour=10, break_between_tasks_minutes=0)
        owner_no_break.add_pet(pet)

        # Add tasks in non-priority order
        task_walk.pet_id = pet.id
        task_feed.pet_id = pet.id
        task_play.pet_id = pet.id

        owner_no_break.add_task(task_play)  # Low priority
        owner_no_break.add_task(task_walk)  # High priority
        owner_no_break.add_task(task_feed)  # High priority

        scheduler = Scheduler(owner_no_break)
        scheduled = scheduler.generate_daily_schedule(datetime(2026, 7, 4))

        # Verify order: high, high, low
        assert scheduled[0][0].priority == Priority.HIGH
        assert scheduled[1][0].priority == Priority.HIGH
        assert scheduled[2][0].priority == Priority.LOW

    def test_start_time_is_work_start(self, owner_custom_hours, pet, task_walk):
        """Verify first task starts at work day start time"""
        owner_custom_hours.add_pet(pet)
        task_walk.pet_id = pet.id
        owner_custom_hours.add_task(task_walk)

        scheduler = Scheduler(owner_custom_hours)
        test_date = datetime(2026, 7, 4, 10, 0, 0)
        scheduled = scheduler.generate_daily_schedule(test_date)

        _, start_time, _ = scheduled[0]
        expected_start = datetime(2026, 7, 4, 9, 30, 0)
        assert start_time == expected_start

    def test_end_time_equals_start_plus_duration(self, owner_with_schedule, pet, task_walk):
        """Verify task end time = start time + duration"""
        owner_with_schedule.add_pet(pet)
        task_walk.pet_id = pet.id
        owner_with_schedule.add_task(task_walk)

        scheduler = Scheduler(owner_with_schedule)
        scheduled = scheduler.generate_daily_schedule(datetime(2026, 7, 4))

        _, start_time, end_time = scheduled[0]
        expected_end = start_time + timedelta(minutes=task_walk.duration)
        assert end_time == expected_end
