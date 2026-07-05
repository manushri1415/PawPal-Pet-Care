"""
Testing ground for PawPal+ system
Demonstrates creating an Owner, Pets, Tasks, and displaying a daily schedule
"""

from datetime import datetime, timedelta
from pawpal_system import Owner, Pet, Task, Category, Priority, Frequency, Scheduler, Gender


def main():
    # Create an owner
    owner = Owner(
        name="Alice Johnson",
        email="alice@example.com",
        phone_number="555-1234",
        available_hours_per_day=4.0
    )

    # Create pets
    dog = Pet(
        name="Max",
        pet_type="Dog",
        age=3,
        gender=Gender.MALE,
        color="Golden Retriever"
    )

    cat = Pet(
        name="Whiskers",
        pet_type="Cat",
        age=5,
        gender=Gender.FEMALE,
        color="Orange Tabby"
    )

    # Add pets to owner
    owner.add_pet(dog)
    owner.add_pet(cat)

    # Create tasks with different times (intentionally out of order)
    task4 = Task(
        name="Feed Whiskers",
        category=Category.FEEDING,
        pet_id=cat.id,
        duration=5,
        priority=Priority.HIGH,
        frequency=Frequency.DAILY,
        scheduled_time="18:00"
    )

    task2 = Task(
        name="Feed Max",
        category=Category.FEEDING,
        pet_id=dog.id,
        duration=10,
        priority=Priority.HIGH,
        frequency=Frequency.DAILY,
        scheduled_time="12:30"
    )

    task3 = Task(
        name="Play with Whiskers",
        category=Category.PLAY,
        pet_id=cat.id,
        duration=20,
        priority=Priority.MEDIUM,
        frequency=Frequency.DAILY,
        scheduled_time="15:00"
    )

    task1 = Task(
        name="Morning Walk",
        category=Category.EXERCISE,
        pet_id=dog.id,
        duration=30,
        priority=Priority.HIGH,
        frequency=Frequency.DAILY,
        scheduled_time="08:00"
    )

    # Add tasks to pets
    owner.add_task(task1)
    owner.add_task(task2)
    owner.add_task(task3)
    owner.add_task(task4)

    # Create scheduler and generate daily schedule
    scheduler = Scheduler(owner)
    daily_schedule = scheduler.generate_daily_schedule()

    # Display results
    print("=" * 60)
    print(f"PawPal+ Daily Schedule for {owner.name}")
    print(f"Date: {datetime.now().strftime('%A, %B %d, %Y')}")
    print("=" * 60)
    print()

    print(f"Owner: {owner.name}")
    print(f"Email: {owner.email}")
    print(f"Available Time: {owner.available_hours_per_day} hours/day")
    print()

    print("PETS:")
    for pet in owner.get_pets():
        print(f"  • {pet.name} ({pet.type}) - {pet.age} years old, {pet.color}")
    print()

    print("TODAY'S SCHEDULE (Prioritized):")
    print("-" * 60)

    if daily_schedule:
        total_time = 0

        for i, (task, start_time, end_time) in enumerate(daily_schedule, 1):
            # Find pet name
            pet_name = "Owner"
            for pet in owner.get_pets():
                if pet.id == task.pet_id:
                    pet_name = pet.name
                    break

            print(f"{i}. [{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}] "
                  f"{task.name} ({task.category.value})")
            print(f"   Pet: {pet_name} | Duration: {task.duration} min | "
                  f"Priority: {task.priority.value}")
            print()

            total_time += task.duration

        print("-" * 60)
        print(f"Total Scheduled Time: {total_time} minutes ({total_time / 60:.1f} hours)")
        print(f"Available Time: {owner.available_hours_per_day * 60:.0f} minutes "
              f"({owner.available_hours_per_day} hours)")
    else:
        print("No tasks scheduled for today.")

    print("=" * 60)

    # Demonstrate sorting and filtering
    print()
    print("=" * 60)
    print("SORTING AND FILTERING DEMONSTRATION")
    print("=" * 60)
    print()

    # Get all tasks
    all_tasks = owner.get_all_tasks_across_pets()

    # Sort by time
    print("Tasks sorted by TIME (earliest first):")
    print("-" * 60)
    sorted_tasks = scheduler.sort_by_time(all_tasks)
    for task in sorted_tasks:
        pet_name = next((p.name for p in owner.get_pets() if p.id == task.pet_id), "Unknown")
        time_str = task.scheduled_time if task.scheduled_time else "No time set"
        print(f"  • {time_str} - {task.name} ({pet_name}) | {task.duration} min")
    print()

    # Filter by pet - Max
    print("Tasks for MAX only:")
    print("-" * 60)
    max_tasks = scheduler.filter_by_pet(all_tasks, "Max")
    for task in max_tasks:
        print(f"  • {task.name} at {task.scheduled_time} | {task.priority.value} priority")
    print()

    # Filter by pet - Whiskers
    print("Tasks for WHISKERS only:")
    print("-" * 60)
    whiskers_tasks = scheduler.filter_by_pet(all_tasks, "Whiskers")
    for task in whiskers_tasks:
        print(f"  • {task.name} at {task.scheduled_time} | {task.priority.value} priority")
    print()

    # Mark some tasks as complete using the new mark_task_complete method
    print("RECURRING TASK AUTOMATION DEMONSTRATION")
    print("=" * 60)
    print()

    if sorted_tasks:
        first_task = sorted_tasks[0]
        print(f"Before completion:")
        print(f"  Total tasks: {len(owner.get_all_tasks_across_pets())}")
        print(f"  Marked task: {first_task.name} (ID: {first_task.id[:8]}...)")
        print(f"  Task frequency: {first_task.frequency.value}")
        print(f"  Task due date: {first_task.due_date.strftime('%Y-%m-%d')}")
        print()

        # Mark task as complete using the scheduler (which handles recurring tasks)
        scheduler.mark_task_complete(first_task.id)

        print(f"After completion:")
        print(f"  Total tasks: {len(owner.get_all_tasks_across_pets())}")
        print()

        # Show the new task that was automatically created
        if first_task.is_recurring() and first_task.frequency != Frequency.AS_NEEDED:
            all_tasks_updated = owner.get_all_tasks_across_pets()
            new_task = next((t for t in all_tasks_updated if t.name == first_task.name and not t.completed), None)
            if new_task:
                print(f"  [NEW] New task automatically created!")
                print(f"    Name: {new_task.name}")
                print(f"    Due date: {new_task.due_date.strftime('%Y-%m-%d')} (next {first_task.frequency.value})")
                print(f"    Completed: {new_task.completed}")
                print()

    # Filter by status - incomplete
    print("INCOMPLETE tasks:")
    print("-" * 60)
    incomplete_tasks = scheduler.filter_by_status(owner.get_all_tasks_across_pets(), completed=False)
    for task in incomplete_tasks:
        pet_name = next((p.name for p in owner.get_pets() if p.id == task.pet_id), "Unknown")
        print(f"  • {task.name} ({pet_name}) at {task.scheduled_time}")
    print()

    # Filter by status - complete
    print("COMPLETED tasks:")
    print("-" * 60)
    complete_tasks = scheduler.filter_by_status(owner.get_all_tasks_across_pets(), completed=True)
    for task in complete_tasks:
        pet_name = next((p.name for p in owner.get_pets() if p.id == task.pet_id), "Unknown")
        print(f"  • {task.name} ({pet_name}) at {task.scheduled_time}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
