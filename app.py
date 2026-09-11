import html
import streamlit as st
import time as time_module
from datetime import time, datetime

from pawpal_system import Task, Pet, Category, Priority, Frequency, Gender, Owner, Scheduler

_MARKDOWN_STRIP_TABLE = str.maketrans("", "", "*_`#")


def sanitize_title(title):
    return title.translate(_MARKDOWN_STRIP_TABLE).strip()

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")

# Shared with the Health Records page's status colors (Overdue/Due soon/Current)
# so "urgent", "soon" and "settled" read the same way everywhere in the app.
PRIORITY_COLORS = {
    "low": "#5F6B45",
    "medium": "#A67A2E",
    "high": "#B14A2C",
}


def priority_badge(priority_value: str) -> str:
    color = PRIORITY_COLORS.get(priority_value, "#6B5B49")
    label = priority_value.capitalize()
    return (
        f'<span style="display:inline-flex; align-items:center; gap:6px; '
        f'font-size:0.85em; font-weight:700; color:{color};">'
        f'<span style="width:7px; height:7px; border-radius:999px; background:{color}; '
        f'display:inline-block;"></span>{label}</span>'
    )


# Shared brand mark — identical snippet used on the Health Records page sidebar,
# for a consistent visual identity across both pages of the app.
BRAND_MARK_HTML = (
    "<div style='display:flex;align-items:center;gap:10px;padding:0 0 18px;'>"
    "<div style='width:32px;height:32px;border-radius:8px;background:#B14A2C;"
    "display:flex;align-items:center;justify-content:center;flex-shrink:0;'>"
    "<svg width='17' height='17' viewBox='0 0 24 24' fill='#F3E9DA'>"
    "<ellipse cx='7' cy='8' rx='2.1' ry='2.6'/><ellipse cx='12' cy='6' rx='2.2' ry='2.8'/>"
    "<ellipse cx='17' cy='8' rx='2.1' ry='2.6'/><ellipse cx='12' cy='15.5' rx='5.2' ry='4.4'/>"
    "</svg></div>"
    "<span style='font-size:19px;font-weight:600;color:#2B2117;'>PawPal+</span></div>"
)

# Pet-avatar icon paths (species-specific line icons), rendered inside a 52px
# circle. Falls back to a plain paw glyph for any species other than dog/cat.
DOG_ICON_PATHS = (
    "<circle cx='12' cy='13.2' r='6.3'/>"
    "<path d='M6.3 9c-2-3-3.1-5.2-1.6-6.2 2-1 4.2 1 5.6 4.2'/>"
    "<path d='M17.7 9c2-3 3.1-5.2 1.6-6.2-2-1-4.2 1-5.6 4.2'/>"
)
CAT_ICON_PATHS = (
    "<circle cx='12' cy='13.6' r='6'/>"
    "<path d='M6.6 8.6 5 3l4.6 4'/>"
    "<path d='M17.4 8.6 19 3l-4.6 4'/>"
)


def pet_avatar_html(species: str) -> str:
    icon_paths = {"dog": DOG_ICON_PATHS, "cat": CAT_ICON_PATHS}.get(species)
    if icon_paths:
        inner = (
            "<svg width='26' height='26' viewBox='0 0 24 24' fill='none' "
            "stroke='#8F3A21' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'>"
            f"{icon_paths}</svg>"
        )
    else:
        inner = "<span style='font-size:22px;line-height:1;'>🐾</span>"
    return (
        "<div style='width:52px;height:52px;border-radius:50%;background:#DFCFAE;"
        "display:flex;align-items:center;justify-content:center;flex-shrink:0;'>"
        f"{inner}</div>"
    )


def pet_card_html(pet) -> str:
    age_str = f"{pet.age} years" if pet.age_months == 0 else f"{pet.age} years {pet.age_months} months"
    meta = f"{pet.type.capitalize()} · {pet.gender.value.capitalize()} · {age_str}"
    return (
        "<div style='display:flex;align-items:center;gap:12px;margin-bottom:6px;'>"
        f"{pet_avatar_html(pet.type)}"
        "<div>"
        f"<div style='font-family:Lora,serif;font-weight:600;font-size:1.05rem;color:#2B2117;'>{html.escape(pet.name)}</div>"
        f"<div style='color:#6B5B49;font-size:0.85rem;'>{html.escape(meta)}</div>"
        "</div></div>"
    )


with st.sidebar:
    st.markdown(BRAND_MARK_HTML, unsafe_allow_html=True)

st.title("🐾 PawPal+")

# st.container(key=...) generates a real, targetable ".st-key-<name>" wrapper
# class around every widget placed inside it — unlike opening/closing raw <div>
# tags across separate st.markdown calls (which render as two unrelated, empty
# sibling elements and wrap nothing), this actually nests the widgets inside
# one styled panel.
st.html("<style>.st-key-profile_panel{background:#E2D5BC;padding:24px;border-radius:4px;}</style>")

top_left, top_right = st.columns([1, 1.3])

with top_left:
    profile_panel = st.container(key="profile_panel")
    with profile_panel:
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
# Only reset owner if user identity changes (name/email); work settings can be updated without losing pets
owner_identity_key = f"{owner_name}_{owner_email}"
if 'owner' not in st.session_state or st.session_state.get('owner_identity_key') != owner_identity_key:
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
    st.session_state.owner_identity_key = owner_identity_key
else:
    # Update work settings without recreating the owner (preserves pets and tasks)
    st.session_state.owner.work_start_hour = work_start.hour
    st.session_state.owner.work_start_minute = work_start.minute
    st.session_state.owner.work_end_hour = work_end.hour
    st.session_state.owner.work_end_minute = work_end.minute
    st.session_state.owner.break_between_tasks_minutes = int(break_duration)
    st.session_state.owner.available_hours_per_day = float(available_hours)

owner = st.session_state.owner

with st.sidebar:
    st.markdown("<div style='border-top:1px solid #D9CBB0;margin:14px 0 14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='padding-bottom:4px;'>"
        f"<div style='font-family:Lora,serif;font-weight:600;font-size:0.95rem;color:#2B2117;'>{html.escape(owner.name)}</div>"
        f"<div style='font-size:0.8rem;color:#6B5B49;'>{work_start.strftime('%H:%M')}–{work_end.strftime('%H:%M')} work day</div>"
        "</div>",
        unsafe_allow_html=True,
    )

with top_right:
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

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Add pet", type="primary"):
            if not pet_name.strip():
                st.error("Please enter a pet name.")
            elif pet_age == 0 and pet_age_months == 0:
                st.error("Please enter a valid age (cannot be 0 years and 0 months).")
            else:
                new_pet = Pet(
                    name=pet_name,
                    pet_type=species,
                    age=int(pet_age),
                    age_months=int(pet_age_months),
                    gender=Gender[pet_gender.upper()]
                )
                owner.add_pet(new_pet)
                st.toast(f"✅ Added {pet_name}!")
                del st.session_state.pet_name
                st.rerun()

    # Display current pets
    pets = owner.get_pets()
    if pets:
        st.subheader("Your Pets")
        for chunk_start in range(0, len(pets), 3):
            chunk = pets[chunk_start:chunk_start + 3]
            pet_cols = st.columns(min(len(chunk), 3))
            for pet_col, pet in zip(pet_cols, chunk):
                with pet_col:
                    st.markdown(pet_card_html(pet), unsafe_allow_html=True)

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("Edit", key=f"edit_pet_{pet.id}"):
                            st.session_state[f"editing_pet_{pet.id}"] = True
                            st.rerun()
                    with btn_col2:
                        if st.button("Delete", key=f"delete_pet_{pet.id}"):
                            owner.pets.remove(pet)
                            st.success(f"Deleted {pet.name}!")
                            st.rerun()

                    if st.session_state.get(f"editing_pet_{pet.id}"):
                        with st.form(key=f"edit_pet_form_{pet.id}"):
                            edit_name = st.text_input("Pet name", value=pet.name, key=f"edit_pet_name_{pet.id}")
                            edit_species = st.selectbox(
                                "Species", ["dog", "cat", "other"],
                                index=["dog", "cat", "other"].index(pet.type) if pet.type in ["dog", "cat", "other"] else 2,
                                key=f"edit_pet_species_{pet.id}"
                            )
                            edit_age = st.number_input("Age (years)", min_value=0, max_value=50, value=pet.age, key=f"edit_pet_age_{pet.id}")
                            edit_age_months = st.number_input("Months", min_value=0, max_value=11, value=pet.age_months, key=f"edit_pet_age_months_{pet.id}")
                            edit_gender = st.selectbox(
                                "Gender", ["male", "female", "unknown"],
                                index=["male", "female", "unknown"].index(pet.gender.value),
                                key=f"edit_pet_gender_{pet.id}"
                            )

                            save_col, cancel_col, _ = st.columns([1, 1, 4])
                            with save_col:
                                save_clicked = st.form_submit_button("Save")
                            with cancel_col:
                                cancel_clicked = st.form_submit_button("Cancel")

                            if save_clicked:
                                if not edit_name.strip():
                                    st.error("Please enter a pet name.")
                                elif edit_age == 0 and edit_age_months == 0:
                                    st.error("Please enter a valid age (cannot be 0 years and 0 months).")
                                else:
                                    pet.name = edit_name
                                    pet.type = edit_species
                                    pet.age = int(edit_age)
                                    pet.age_months = int(edit_age_months)
                                    pet.gender = Gender[edit_gender.upper()]
                                    del st.session_state[f"editing_pet_{pet.id}"]
                                    st.success(f"Updated {edit_name}!")
                                    st.rerun()
                            if cancel_clicked:
                                del st.session_state[f"editing_pet_{pet.id}"]
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

    task_frequency = st.selectbox(
        "Repeats", [f.value for f in Frequency],
        index=[f.value for f in Frequency].index("once"),
        key="task_frequency"
    )

    task_end_date = None
    if task_frequency not in ("once", "as_needed"):
        col1, col2 = st.columns([1, 2])
        with col1:
            no_end_repeat = st.checkbox("Never ends", value=True, key="task_no_end_repeat")
        with col2:
            task_end_date = None if no_end_repeat else st.date_input("End repeat on", key="task_end_repeat_date")

    col1, col2 = st.columns([1, 2])
    with col1:
        no_preferred_time = st.checkbox("No preferred time", value=True, key="task_no_preferred_time")
    with col2:
        preferred_time = None if no_preferred_time else st.time_input("Preferred time", value=None, key="task_preferred_time")

    task_notes = st.text_area("Notes (optional)", value="", placeholder="e.g., Medication: amoxicillin, Diet: chicken breast", height=60)

    if st.button("Add task", type="primary"):
        clean_title = sanitize_title(task_title)
        if clean_title:
            total_duration = int(duration_hours) * 60 + int(duration_minutes)
            if total_duration == 0:
                st.error("Duration must be at least 1 minute.")
            else:
                scheduled_time = preferred_time.strftime("%H:%M") if preferred_time is not None else ""
                end_date_value = (
                    datetime.combine(task_end_date, time(0, 0)) if task_end_date is not None else None
                )
                new_task = Task(
                    name=clean_title,
                    category=Category[task_category.upper()],
                    pet_id=selected_pet_obj.id,
                    duration=total_duration,
                    priority=Priority[task_priority.upper()],
                    frequency=Frequency(task_frequency),
                    notes=task_notes,
                    scheduled_time=scheduled_time,
                    end_date=end_date_value
                )
                owner.add_task(new_task)
                st.success(f"Added '{clean_title}' to {selected_pet}")
                st.rerun()
        else:
            st.error("Please enter a task title.")
else:
    st.warning("Add a pet first before creating tasks.")

# Display all tasks across pets
all_tasks = owner.get_all_tasks_across_pets()
if all_tasks:
    st.subheader("All Tasks")

    scheduler = Scheduler(owner)
    pet_filter_options = ["All pets"] + [p.name for p in owner.get_pets()]
    pet_filter = st.selectbox("Filter by pet", pet_filter_options, key="task_pet_filter")

    filtered_tasks = all_tasks if pet_filter == "All pets" else scheduler.filter_by_pet(all_tasks, pet_filter)
    incomplete_tasks = scheduler.filter_by_status(filtered_tasks, completed=False)
    completed_tasks = scheduler.filter_by_status(filtered_tasks, completed=True)

    # Warn immediately if any tasks with a preferred time overlap, without
    # requiring the owner to click "Generate schedule" first.
    timed_tasks = [t for t in incomplete_tasks if t.scheduled_time]
    overlap_pairs = []
    for i, t1 in enumerate(timed_tasks):
        start1_h, start1_m = map(int, t1.scheduled_time.split(":"))
        start1 = start1_h * 60 + start1_m
        end1 = start1 + t1.duration
        for t2 in timed_tasks[i + 1:]:
            start2_h, start2_m = map(int, t2.scheduled_time.split(":"))
            start2 = start2_h * 60 + start2_m
            end2 = start2 + t2.duration
            if start1 < end2 and start2 < end1:
                overlap_pairs.append((t1, t2))

    if overlap_pairs:
        for t1, t2 in overlap_pairs:
            st.warning(
                f"⚠️ '{t1.name}' ({t1.scheduled_time}) overlaps with '{t2.name}' ({t2.scheduled_time})."
            )

    if not incomplete_tasks:
        st.info("No open tasks. Nice work!" if completed_tasks else "No tasks match this filter.")

    for task in incomplete_tasks:
        pet = next((p for p in owner.get_pets() if p.id == task.pet_id), None)
        pet_name = pet.name if pet else "Unknown"
        hours = task.duration // 60
        minutes = task.duration % 60
        duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        time_str = f" at {task.scheduled_time}" if task.scheduled_time else ""
        end_repeat_str = f", ends {task.end_date.strftime('%b %d')}" if task.end_date else ""
        frequency_str = (
            f" | 🔁 {task.frequency.value} (next due {task.due_date.strftime('%b %d')}{end_repeat_str})"
            if task.frequency != Frequency.ONCE else ""
        )

        col0, col1, col2, col3 = st.columns([0.5, 4.5, 1, 1])
        with col0:
            if st.checkbox("Mark complete", value=False, key=f"complete_task_{task.id}", label_visibility="collapsed"):
                scheduler.mark_task_complete(task.id)
                if task.is_recurring():
                    st.toast(f"'{task.name}' completed — next occurrence scheduled.")
                else:
                    st.toast(f"'{task.name}' completed!")
                st.rerun()
        with col1:
            st.markdown(
                f"**{html.escape(task.name)}** ({task.category.value}) - {duration_str}{time_str} | {html.escape(pet_name)}{frequency_str} &nbsp; "
                f"{priority_badge(task.priority.value)}",
                unsafe_allow_html=True
            )
            if task.notes:
                st.caption(f"{task.notes}")
        with col2:
            if st.button("Edit", key=f"edit_task_{task.id}"):
                st.session_state[f"editing_task_{task.id}"] = True
                st.rerun()
        with col3:
            if st.button("Delete", key=f"delete_task_{task.id}"):
                owner.delete_task(task.id)
                st.success(f"Deleted '{task.name}'!")
                st.rerun()

        if st.session_state.get(f"editing_task_{task.id}"):
            with st.form(key=f"edit_task_form_{task.id}"):
                edit_title = st.text_input("Task title", value=task.name, key=f"edit_title_{task.id}")
                edit_category = st.selectbox(
                    "Category", [c.value for c in Category],
                    index=[c.value for c in Category].index(task.category.value),
                    key=f"edit_category_{task.id}"
                )
                edit_priority = st.selectbox(
                    "Priority", ["high", "medium", "low"],
                    index=["high", "medium", "low"].index(task.priority.value),
                    key=f"edit_priority_{task.id}"
                )
                edit_hours = st.number_input("Duration (hours)", min_value=0, max_value=23, value=task.duration // 60, key=f"edit_hours_{task.id}")
                edit_minutes = st.number_input("Duration (minutes)", min_value=0, max_value=59, value=task.duration % 60, key=f"edit_minutes_{task.id}")
                edit_frequency = st.selectbox(
                    "Repeats", [f.value for f in Frequency],
                    index=[f.value for f in Frequency].index(task.frequency.value),
                    key=f"edit_frequency_{task.id}"
                )

                edit_end_date = None
                if edit_frequency not in ("once", "as_needed"):
                    edit_no_end_repeat = st.checkbox(
                        "Never ends", value=task.end_date is None, key=f"edit_no_end_repeat_{task.id}"
                    )
                    edit_end_date = None if edit_no_end_repeat else st.date_input(
                        "End repeat on",
                        value=task.end_date.date() if task.end_date else None,
                        key=f"edit_end_repeat_date_{task.id}"
                    )

                # Parse existing scheduled_time if it exists
                if task.scheduled_time:
                    hours, minutes = map(int, task.scheduled_time.split(":"))
                    edit_preferred_time_value = time(hour=hours, minute=minutes)
                else:
                    edit_preferred_time_value = None
                edit_no_preferred_time = st.checkbox(
                    "No preferred time", value=task.scheduled_time == "", key=f"edit_no_preferred_time_{task.id}"
                )
                edit_preferred_time = None if edit_no_preferred_time else st.time_input(
                    "Preferred time", value=edit_preferred_time_value, key=f"edit_preferred_time_{task.id}"
                )

                edit_notes = st.text_area("Notes (optional)", value=task.notes, key=f"edit_notes_{task.id}")

                save_col, cancel_col, _ = st.columns([1,1, 4])
                with save_col:
                    save_clicked = st.form_submit_button("Save")
                with cancel_col:
                    cancel_clicked = st.form_submit_button("Cancel")

                if save_clicked:
                    clean_edit_title = sanitize_title(edit_title)
                    if not clean_edit_title:
                        st.error("Please enter a task title.")
                    else:
                        total_duration = int(edit_hours) * 60 + int(edit_minutes)
                        if total_duration == 0:
                            st.error("Duration must be at least 1 minute.")
                        else:
                            edit_scheduled_time = edit_preferred_time.strftime("%H:%M") if edit_preferred_time is not None else ""
                            edit_end_date_value = (
                                datetime.combine(edit_end_date, time(0, 0)) if edit_end_date is not None else None
                            )
                            owner.edit_task(task.id, {
                                "name": clean_edit_title,
                                "category": Category[edit_category.upper()],
                                "priority": Priority[edit_priority.upper()],
                                "duration": total_duration,
                                "frequency": Frequency(edit_frequency),
                                "notes": edit_notes,
                                "scheduled_time": edit_scheduled_time,
                                "end_date": edit_end_date_value,
                            })
                            del st.session_state[f"editing_task_{task.id}"]
                            st.success(f"Updated '{clean_edit_title}'!")
                            st.rerun()
                if cancel_clicked:
                    del st.session_state[f"editing_task_{task.id}"]
                    st.rerun()

        st.markdown("<div style='border-bottom:1px solid #D9CBB0;margin:2px 0 10px;'></div>", unsafe_allow_html=True)

    if completed_tasks:
        with st.expander(f"✅ Completed ({len(completed_tasks)})"):
            for task in completed_tasks:
                pet = next((p for p in owner.get_pets() if p.id == task.pet_id), None)
                pet_name = pet.name if pet else "Unknown"

                col0, col1, col2 = st.columns([0.5, 4.5, 1])
                with col0:
                    if not st.checkbox("Mark complete", value=True, key=f"complete_task_{task.id}", label_visibility="collapsed"):
                        task.completed = False
                        st.rerun()
                with col1:
                    st.markdown(f"~~**{task.name}**~~ ({task.category.value}) | {pet_name}")
                with col2:
                    if st.button("Delete", key=f"delete_task_{task.id}"):
                        owner.delete_task(task.id)
                        st.success(f"Deleted '{task.name}'!")
                        st.rerun()
else:
    st.info("No tasks yet. Add one above.")

st.divider()

st.subheader("Build Schedule")
st.caption("Generates a schedule sorted by priority, checks for time conflicts, and lets you sort the view.")

sort_labels = {
    "Priority (high → low)": "Priority",
    "Time (earliest first)": "Time",
    "Duration (shortest first)": "Duration"
}
sort_option_label = st.selectbox(
    "Sort display by",
    list(sort_labels.keys()),
    key="sort_option"
)
sort_option = sort_labels[sort_option_label]

if st.button("Generate schedule", type="primary"):
    if not owner.get_pets():
        st.warning("Add at least one pet first.")
    elif not owner.get_all_tasks_across_pets():
        st.warning("Add at least one task first.")
    else:
        with st.spinner("Generating schedule..."):
            time_module.sleep(0.4)
            scheduler = Scheduler(owner)
            scheduled_tasks = scheduler.generate_daily_schedule()

        if scheduled_tasks:
            st.subheader("Your Daily Schedule")
            st.caption(f"Work hours: {work_start.strftime('%H:%M')} - {work_end.strftime('%H:%M')} | Break between tasks: {break_duration} min")

            total_duration = sum(t[0].duration for t in scheduled_tasks)
            total_hours = total_duration // 60
            total_minutes = total_duration % 60
            total_str = f"{total_hours}h {total_minutes}m" if total_hours > 0 else f"{total_minutes}m"
            st.success(f"Scheduled {len(scheduled_tasks)} task(s) totaling {total_str}.")

            # Conflict warnings shown up front so they're impossible to miss
            conflicts = scheduler.detect_conflicts(scheduled_tasks)
            if conflicts:
                st.warning(
                    f"⚠️ {len(conflicts)} scheduling conflict(s) detected — double-check these overlaps:"
                )
                for warning in conflicts:
                    st.error(warning)

            # Re-sort the display order per the owner's chosen view, independent of the
            # priority-based order used to actually pack tasks into the day
            display_tasks = [t for t, _, _ in scheduled_tasks]
            if sort_option == "Time":
                display_order = scheduler.sort_by_time(display_tasks)
            elif sort_option == "Duration":
                display_order = scheduler.sort_by_duration(display_tasks)
            else:
                display_order = scheduler.sort_by_priority(display_tasks)

            slot_by_task_id = {task.id: (start_time, end_time) for task, start_time, end_time in scheduled_tasks}

            table_rows = []
            for task in display_order:
                start_time, end_time = slot_by_task_id[task.id]
                pet = next((p for p in owner.get_pets() if p.id == task.pet_id), None)
                table_rows.append({
                    "Time": f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}",
                    "Task": task.name,
                    "Pet": pet.name if pet else "Unknown",
                    "Duration": f"{task.duration}m",
                    "Priority": task.priority.value,
                    "Category": task.category.value,
                })
            st.table(table_rows)
        else:
            st.info("No tasks fit in your available time.")
