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


class TestSortingChronological:
    """Tests for Scheduler.sort_by_time() chronological ordering"""

    def test_sort_by_time_returns_chronological_order(self, pet):
        """Verify tasks are returned in ascending order by scheduled_time"""
        task_evening = Task(name="Evening Walk", category=Category.EXERCISE, pet_id=pet.id,
                             duration=30, scheduled_time="18:00")
        task_morning = Task(name="Morning Feed", category=Category.FEEDING, pet_id=pet.id,
                             duration=15, scheduled_time="07:00")
        task_afternoon = Task(name="Afternoon Play", category=Category.PLAY, pet_id=pet.id,
                               duration=20, scheduled_time="13:00")

        owner = Owner(name="TestOwner")
        scheduler = Scheduler(owner)

        sorted_tasks = scheduler.sort_by_time([task_evening, task_morning, task_afternoon])

        assert [t.name for t in sorted_tasks] == ["Morning Feed", "Afternoon Play", "Evening Walk"]

    def test_sort_by_time_pushes_unscheduled_tasks_last(self, pet):
        """Tasks without a scheduled_time should sort after all timed tasks"""
        task_timed = Task(name="Timed", category=Category.PLAY, pet_id=pet.id,
                           duration=10, scheduled_time="09:00")
        task_untimed = Task(name="Untimed", category=Category.PLAY, pet_id=pet.id, duration=10)

        owner = Owner(name="TestOwner")
        scheduler = Scheduler(owner)

        sorted_tasks = scheduler.sort_by_time([task_untimed, task_timed])

        assert [t.name for t in sorted_tasks] == ["Timed", "Untimed"]


class TestRecurrenceLogic:
    """Tests for automatic recurring task generation on completion"""

    def test_completing_daily_task_creates_next_day_occurrence(self, owner_with_pet):
        """Marking a DAILY task complete should generate a new task due the next day"""
        pet = owner_with_pet.get_pets()[0]
        original_due = datetime(2026, 7, 4)

        task = Task(
            name="Daily Feed",
            category=Category.FEEDING,
            pet_id=pet.id,
            duration=10,
            frequency=Frequency.DAILY,
            due_date=original_due
        )
        pet.add_task(task)

        result = owner_with_pet.mark_task_complete(task.id)

        assert result is True
        assert task.completed is True
        assert len(pet.get_tasks()) == 2

        new_task = [t for t in pet.get_tasks() if t.id != task.id][0]
        assert new_task.name == "Daily Feed"
        assert new_task.completed is False
        assert new_task.due_date == original_due + timedelta(days=1)

    def test_completing_once_task_does_not_create_new_occurrence(self, owner_with_pet, task_play):
        """A ONCE task should not spawn a next occurrence when completed"""
        pet = owner_with_pet.get_pets()[0]
        task_play.pet_id = pet.id
        pet.add_task(task_play)

        owner_with_pet.mark_task_complete(task_play.id)

        assert len(pet.get_tasks()) == 1


class TestConflictDetection:
    """Tests for Scheduler.detect_conflicts()"""

    def test_detects_overlapping_tasks(self, owner_with_pet, pet):
        """Two tasks scheduled at overlapping times should produce a conflict warning"""
        task1 = Task(name="Walk", category=Category.EXERCISE, pet_id=pet.id, duration=30)
        task2 = Task(name="Grooming", category=Category.GROOMING, pet_id=pet.id, duration=30)

        start = datetime(2026, 7, 4, 9, 0)
        schedule = [
            (task1, start, start + timedelta(minutes=30)),
            (task2, start + timedelta(minutes=15), start + timedelta(minutes=45)),  # overlaps task1
        ]

        scheduler = Scheduler(owner_with_pet)
        warnings = scheduler.detect_conflicts(schedule)

        assert len(warnings) == 1
        assert "Walk" in warnings[0]
        assert "Grooming" in warnings[0]

    def test_back_to_back_tasks_are_not_conflicts(self, owner_with_pet, pet):
        """Tasks that end exactly when the next starts should not be flagged"""
        task1 = Task(name="Walk", category=Category.EXERCISE, pet_id=pet.id, duration=30)
        task2 = Task(name="Feed", category=Category.FEEDING, pet_id=pet.id, duration=30)

        start = datetime(2026, 7, 4, 9, 0)
        end1 = start + timedelta(minutes=30)
        schedule = [
            (task1, start, end1),
            (task2, end1, end1 + timedelta(minutes=30)),
        ]

        scheduler = Scheduler(owner_with_pet)
        warnings = scheduler.detect_conflicts(schedule)

        assert warnings == []
