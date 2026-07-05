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

    # Create tasks with different times
    task1 = Task(
        name="Morning Walk",
        category=Category.EXERCISE,
        pet_id=dog.id,
        duration=30,
        priority=Priority.HIGH,
        frequency=Frequency.DAILY
    )

    task2 = Task(
        name="Feed Max",
        category=Category.FEEDING,
        pet_id=dog.id,
        duration=10,
        priority=Priority.HIGH,
        frequency=Frequency.DAILY
    )

    task3 = Task(
        name="Play with Whiskers",
        category=Category.PLAY,
        pet_id=cat.id,
        duration=20,
        priority=Priority.MEDIUM,
        frequency=Frequency.DAILY
    )

    task4 = Task(
        name="Feed Whiskers",
        category=Category.FEEDING,
        pet_id=cat.id,
        duration=5,
        priority=Priority.HIGH,
        frequency=Frequency.DAILY
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
        current_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        total_time = 0

        for i, task in enumerate(daily_schedule, 1):
            # Find pet name
            pet_name = "Owner"
            for pet in owner.get_pets():
                if pet.id == task.pet_id:
                    pet_name = pet.name
                    break

            # Calculate scheduled time
            start_time = current_time
            end_time = start_time + timedelta(minutes=task.duration)
            current_time = end_time

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


if __name__ == "__main__":
    main()
