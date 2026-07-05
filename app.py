import streamlit as st

from pawpal_system import Task, Pet, Category, Priority, Frequency, Gender, Owner, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.subheader("Your Profile")
col1, col2 = st.columns(2)
with col1:
    owner_name = st.text_input("Your name", value="Jordan", key="owner_name")
with col2:
    owner_email = st.text_input("Your email", value="jordan@pawpal.com", key="owner_email")

st.subheader("Work Schedule")
col1, col2 = st.columns(2)
with col1:
    work_start = st.time_input("Work start time", value="08:00", key="work_start")
with col2:
    work_end = st.time_input("Work end time", value="18:00", key="work_end")

col1, col2 = st.columns(2)
with col1:
    break_duration = st.number_input("Break between tasks (minutes)", min_value=0, max_value=120, value=15, key="break_duration")
with col2:
    available_hours = st.number_input("Available hours per day", min_value=1, max_value=24, value=8, key="available_hours")

# Initialize or update Owner in session state
owner_key = f"{owner_name}_{owner_email}_{work_start}_{work_end}_{break_duration}_{available_hours}"
if 'owner' not in st.session_state or st.session_state.get('owner_key') != owner_key:
    st.session_state.owner = Owner(
        name=owner_name,
        email=owner_email,
        work_start_hour=work_start.hour,
        work_start_minute=work_start.minute,
        work_end_hour=work_end.hour,
        work_end_minute=work_end.minute,
        break_between_tasks_minutes=int(break_duration),
        available_hours_per_day=float(available_hours)
    )
    st.session_state.owner_key = owner_key

owner = st.session_state.owner

st.subheader("Add a Pet")
st.caption("Add a pet to your owner profile.")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    pet_name = st.text_input("Pet name", value="", key="pet_name")
with col2:
    species = st.selectbox("Species", ["dog", "cat", "other"])
with col3:
    pet_age = st.number_input("Age (years)", min_value=0, max_value=50, value=0)
with col4:
    pet_age_months = st.number_input("Months", min_value=0, max_value=11, value=0)
with col5:
    pet_gender = st.selectbox("Gender", ["male", "female", "unknown"])

if st.button("Add pet"):
    if pet_name.strip():
        new_pet = Pet(
            name=pet_name,
            pet_type=species,
            age=int(pet_age),
            age_months=int(pet_age_months),
            gender=Gender[pet_gender.upper()]
        )
        owner.add_pet(new_pet)
        st.success(f"Added {pet_name} to your pets!")
        st.rerun()
    else:
        st.error("Please enter a pet name.")

# Display current pets
if owner.get_pets():
    st.subheader("Your Pets")
    for pet in owner.get_pets():
        col1, col2 = st.columns([4, 1])
        with col1:
            age_str = f"{pet.age} years" if pet.age_months == 0 else f"{pet.age} years {pet.age_months} months"
            st.write(f"🐾 **{pet.name}** ({pet.type}, {age_str}, {pet.gender.value})")
        with col2:
            if st.button("Delete", key=f"delete_pet_{pet.id}"):
                owner.pets.remove(pet)
                st.success(f"Deleted {pet.name}!")
                st.rerun()
else:
    st.info("No pets yet. Add one above.")

st.divider()

st.subheader("Add a Task")
st.caption("Add a task for your pet(s).")

if owner.get_pets():
    selected_pet = st.selectbox("Select pet", [p.name for p in owner.get_pets()], key="pet_select")
    selected_pet_obj = next(p for p in owner.get_pets() if p.name == selected_pet)

    col1, col2, col3 = st.columns(3)
    with col1:
        task_title = st.text_input("Task title", value="", key="task_title")
    with col2:
        task_category = st.selectbox("Category", [c.value for c in Category])
    with col3:
        task_priority = st.selectbox("Priority", ["high", "medium", "low"], index=2)

    col1, col2 = st.columns(2)
    with col1:
        duration_hours = st.number_input("Duration (hours)", min_value=0, max_value=23, value=0)
    with col2:
        duration_minutes = st.number_input("Duration (minutes)", min_value=0, max_value=59, value=0)

    task_notes = st.text_area("Notes (optional)", value="", placeholder="e.g., Medication: amoxicillin, Diet: chicken breast", height=60)

    if st.button("Add task"):
        if task_title.strip():
            total_duration = int(duration_hours) * 60 + int(duration_minutes)
            if total_duration == 0:
                st.error("Duration must be at least 1 minute.")
            else:
                new_task = Task(
                    name=task_title,
                    category=Category[task_category.upper()],
                    pet_id=selected_pet_obj.id,
                    duration=total_duration,
                    priority=Priority[task_priority.upper()],
                    frequency=Frequency.ONCE,
                    notes=task_notes
                )
                owner.add_task(new_task)
                st.success(f"Added '{task_title}' to {selected_pet}")
                st.rerun()
        else:
            st.error("Please enter a task title.")
else:
    st.warning("Add a pet first before creating tasks.")

# Display all tasks across pets
all_tasks = owner.get_all_tasks_across_pets()
if all_tasks:
    st.subheader("All Tasks")
    for task in all_tasks:
        pet = next((p for p in owner.get_pets() if p.id == task.pet_id), None)
        pet_name = pet.name if pet else "Unknown"
        hours = task.duration // 60
        minutes = task.duration % 60
        duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        st.write(f"✓ **{task.name}** ({task.category.value}) - {duration_str} | {task.priority.value} priority | {pet_name}")
        if task.notes:
            st.caption(f"{task.notes}")
else:
    st.info("No tasks yet. Add one above.")

st.divider()

st.subheader("Build Schedule")
st.caption("This button should call your scheduling logic once you implement it.")

if st.button("Generate schedule"):
    if not owner.get_pets():
        st.warning("Add at least one pet first.")
    elif not owner.get_all_tasks_across_pets():
        st.warning("Add at least one task first.")
    else:
        scheduler = Scheduler(owner)
        scheduled_tasks = scheduler.generate_daily_schedule()

        if scheduled_tasks:
            st.subheader("Your Daily Schedule")
            st.caption(f"Work hours: {work_start.strftime('%H:%M')} - {work_end.strftime('%H:%M')} | Break between tasks: {break_duration} min")

            total_duration = sum(t[0].duration for t in scheduled_tasks)
            total_hours = total_duration // 60
            total_minutes = total_duration % 60
            total_str = f"{total_hours}h {total_minutes}m" if total_hours > 0 else f"{total_minutes}m"
            st.write(f"**Tasks scheduled:** {len(scheduled_tasks)} | **Total time:** {total_str}")

            for i, (task, start_time, end_time) in enumerate(scheduled_tasks, 1):
                pet = next((p for p in owner.get_pets() if p.id == task.pet_id), None)
                pet_name = pet.name if pet else "Unknown"
                start_str = start_time.strftime("%H:%M")
                end_str = end_time.strftime("%H:%M")
                st.write(f"{i}. **{start_str} - {end_str}: {task.name}** ({task.duration}m) - {pet_name} | {task.priority.value} priority")
        else:
            st.info("No tasks fit in your available time.")
