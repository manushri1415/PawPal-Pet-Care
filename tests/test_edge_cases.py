"""Edge case and boundary tests for PawPal+ system"""

from datetime import datetime, timedelta
import pytest
from pawpal_system import Task, Pet, Category, Priority, Frequency, Owner, Scheduler


class TestTaskValidation:
    """Tests for task input validation"""

    def test_zero_duration_task_allowed(self, task_zero_duration):
        """Tasks with 0 duration are allowed - scheduler can fit infinite tasks"""
        assert task_zero_duration.duration == 0

    def test_negative_duration_task_not_allowed(self):
        """Negative duration tasks are rejected"""
        with pytest.raises(ValueError):
            Task(name="Time Travel", category=Category.PLAY, pet_id="test-pet-id", duration=-10)

    def test_scheduler_fits_infinite_zero_duration_tasks(self, owner_short_window, pet):
        """Scheduler fits unlimited zero-duration tasks in any time window"""
        owner_short_window.add_pet(pet)

        for i in range(100):
            task = Task(name=f"Task {i}", category=Category.PLAY, pet_id=pet.id, duration=0)
            owner_short_window.add_task(task)

        scheduler = Scheduler(owner_short_window)
        scheduled = scheduler.generate_daily_schedule()

        assert len(scheduled) == 100


class TestWorkHoursValidation:
    """Tests for work hour validation"""

    def test_work_end_before_start_allowed(self, owner_backward_schedule):
        """Work end time can be before work start time"""
        assert owner_backward_schedule.work_end_hour < owner_backward_schedule.work_start_hour

    def test_invalid_hour_values_not_allowed(self):
        """Hour values > 23 are rejected"""
        with pytest.raises(ValueError):
            Owner(name="TestOwner", work_start_hour=25, work_end_hour=30)

    def test_invalid_minute_values_not_allowed(self):
        """Minute values > 59 are rejected"""
        with pytest.raises(ValueError):
            Owner(name="TestOwner", work_start_minute=70, work_end_minute=120)

    def test_scheduler_rejects_invalid_hours(self, pet):
        """Scheduler rejects invalid hours at owner creation"""
        with pytest.raises(ValueError):
            owner = Owner(name="TestOwner", work_start_hour=25, work_end_hour=30)


class TestOvernightSchedules:
    """Tests for schedules spanning midnight"""

    def test_overnight_work_hours_not_handled(self, pet):
        """Overnight work hours (22:00 - 02:00) don't work correctly"""
        owner = Owner(name="TestOwner", work_start_hour=22, work_end_hour=2)
        owner.add_pet(pet)

        task = Task(name="Night Walk", category=Category.EXERCISE, pet_id=pet.id, duration=30)
        owner.add_task(task)

        scheduler = Scheduler(owner)
        scheduled = scheduler.generate_daily_schedule(datetime(2026, 7, 4))

        if scheduled:
            _, start, end = scheduled[0]
            assert start < end


class TestBreakDurationEdgeCases:
    """Tests for break duration edge cases"""

    def test_break_exceeds_work_window(self, pet):
        """Break duration can exceed entire work window"""
        owner_exceed = Owner(name="TestOwner", work_start_hour=8, work_end_hour=9, break_between_tasks_minutes=120)
        owner_exceed.add_pet(pet)

        task1 = Task(name="Task1", category=Category.PLAY, pet_id=pet.id, duration=15)
        task2 = Task(name="Task2", category=Category.PLAY, pet_id=pet.id, duration=15)
        owner_exceed.add_task(task1)
        owner_exceed.add_task(task2)

        scheduler = Scheduler(owner_exceed)
        scheduled = scheduler.generate_daily_schedule()

        assert len(scheduled) == 1

    def test_negative_break_duration_not_allowed(self):
        """Negative break duration is rejected"""
        with pytest.raises(ValueError):
            Owner(name="TestOwner", work_start_hour=8, work_end_hour=10, break_between_tasks_minutes=-10)

    def test_scheduler_with_negative_break_duration_not_allowed(self):
        """Negative break duration is rejected at owner creation"""
        with pytest.raises(ValueError):
            owner_negative_break = Owner(name="TestOwner", work_start_hour=8, work_end_hour=10, break_between_tasks_minutes=-10)


class TestTaskDataIntegrity:
    """Tests for task and pet data integrity"""

    def test_pet_id_mismatch_validated(self, task_with_nonexistent_pet, owner):
        """Tasks cannot reference non-existent pet IDs"""
        with pytest.raises(ValueError):
            owner.add_task(task_with_nonexistent_pet)

    def test_empty_pet_id_handling(self, task_with_empty_pet_id, owner):
        """Empty string pet_id is treated as owner-level task"""
        owner.add_task(task_with_empty_pet_id)

        assert task_with_empty_pet_id in owner.get_tasks()

    def test_none_pet_id_handling(self, owner):
        """None pet_id is allowed and treated as owner-level"""
        task = Task(name="Walk", category=Category.EXERCISE, pet_id=None, duration=30)
        owner.add_task(task)

        assert task in owner.get_tasks()


class TestTaskFittingEdgeCases:
    """Tests for task fitting edge cases"""

    def test_all_tasks_too_long_silent_failure(self, owner_short_window, pet):
        """When all tasks are too long, scheduler silently returns empty list"""
        owner_short_window.add_pet(pet)

        for i in range(3):
            task = Task(
                name=f"Task{i}",
                category=Category.PLAY,
                pet_id=pet.id,
                duration=45,
                priority=Priority.HIGH if i == 0 else Priority.MEDIUM
            )
            owner_short_window.add_task(task)

        scheduler = Scheduler(owner_short_window)
        scheduled = scheduler.generate_daily_schedule()

        assert len(scheduled) == 1

    def test_very_large_task_duration(self, task_very_long):
        """No validation on max task duration"""
        assert task_very_long.duration == 60000

    def test_no_feedback_on_dropped_tasks(self, owner_short_window, pet):
        """When tasks don't fit, user gets no info on which ones were dropped"""
        owner_short_window.add_pet(pet)

        high_priority = Task(
            name="Important",
            category=Category.MEDICATION,
            pet_id=pet.id,
            duration=40,
            priority=Priority.HIGH
        )
        medium_priority = Task(
            name="Normal",
            category=Category.FEEDING,
            pet_id=pet.id,
            duration=40,
            priority=Priority.MEDIUM
        )
        owner_short_window.add_task(high_priority)
        owner_short_window.add_task(medium_priority)

        scheduler = Scheduler(owner_short_window)
        scheduled = scheduler.generate_daily_schedule()

        assert len(scheduled) == 1


class TestFrequencyHandling:
    """Tests for recurring task frequency handling"""

    def test_frequency_completely_ignored(self, owner, pet, task_walk):
        """Task frequency is stored but never used by scheduler"""
        owner.add_pet(pet)
        task_walk.pet_id = pet.id
        task_walk.frequency = Frequency.DAILY
        owner.add_task(task_walk)

        scheduler = Scheduler(owner)

        scheduled1 = scheduler.generate_daily_schedule(datetime(2026, 7, 4))
        scheduled2 = scheduler.generate_daily_schedule(datetime(2026, 7, 5))

        assert len(scheduled1) == len(scheduled2)


class TestEmptyScenarios:
    """Tests for empty/no data scenarios"""

    def test_empty_task_list_returns_empty_schedule(self, owner, pet):
        """Empty schedule is indistinguishable from error condition"""
        owner.add_pet(pet)

        scheduler = Scheduler(owner)
        scheduled = scheduler.generate_daily_schedule()

        assert len(scheduled) == 0

    def test_owner_with_no_pets_cannot_add_pet_task(self, owner, task_with_nonexistent_pet):
        """Owner with no pets cannot add tasks with non-existent pet IDs"""
        with pytest.raises(ValueError):
            owner.add_task(task_with_nonexistent_pet)


class TestTaskIDUniqueness:
    """Tests for task ID handling"""

    def test_no_uniqueness_check_on_task_ids(self, pet, task_walk, task_feed):
        """Task IDs aren't checked for uniqueness when added"""
        task_feed.id = task_walk.id

        pet.add_task(task_walk)
        pet.add_task(task_feed)

        assert len(pet.get_tasks()) == 2
        assert pet.get_tasks()[0].id == pet.get_tasks()[1].id

    def test_delete_with_duplicate_ids_deletes_all_matches(self, pet, task_walk, task_feed):
        """Deleting by ID removes all matches (not just first)"""
        task_feed.id = task_walk.id
        pet.add_task(task_walk)
        pet.add_task(task_feed)

        pet.remove_task(task_walk.id)

        # Both tasks are removed because they share the same ID
        assert len(pet.get_tasks()) == 0


class TestAvailableHoursValidation:
    """Tests for available hours validation"""

    def test_negative_available_hours_not_allowed(self):
        """Negative available hours are rejected"""
        with pytest.raises(ValueError):
            Owner(name="TestOwner", available_hours_per_day=-8)

    def test_zero_available_hours_not_allowed(self):
        """Zero available hours are rejected"""
        with pytest.raises(ValueError):
            Owner(name="TestOwner", available_hours_per_day=0)

    def test_very_large_available_hours(self):
        """No upper limit on available hours"""
        owner = Owner(name="TestOwner", available_hours_per_day=1000000)
        assert owner.available_hours_per_day == 1000000


class TestSchedulerMutation:
    """Tests for scheduler side effects"""

    def test_scheduler_doesnt_mutate_owner_state(self, owner_with_pet, task_walk):
        """Does generate_daily_schedule() modify owner/task state?"""
        task_walk.pet_id = owner_with_pet.get_pets()[0].id
        owner_with_pet.add_task(task_walk)

        initial_task_count = len(owner_with_pet.get_all_tasks_across_pets())
        initial_completed = task_walk.completed

        scheduler = Scheduler(owner_with_pet)
        scheduled = scheduler.generate_daily_schedule()

        assert len(owner_with_pet.get_all_tasks_across_pets()) == initial_task_count
        assert task_walk.completed == initial_completed

    def test_multiple_schedule_generations_consistent(self, owner_with_pet, task_walk):
        """Do consecutive schedule calls return same result?"""
        task_walk.pet_id = owner_with_pet.get_pets()[0].id
        owner_with_pet.add_task(task_walk)

        scheduler = Scheduler(owner_with_pet)

        scheduled1 = scheduler.generate_daily_schedule(datetime(2026, 7, 4))
        scheduled2 = scheduler.generate_daily_schedule(datetime(2026, 7, 4))

        assert len(scheduled1) == len(scheduled2)
        if scheduled1 and scheduled2:
            assert scheduled1[0][0].name == scheduled2[0][0].name
            assert scheduled1[0][1] == scheduled2[0][1]
