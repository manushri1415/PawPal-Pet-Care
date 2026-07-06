"""Streamlit AppTest integration tests for the Build Schedule sort options in app.py.

Regression coverage for a bug where st.selectbox was given a dict as its
options argument. Streamlit iterates dict options as their keys, so
sort_option ended up holding the display label (e.g. "Duration (shortest
first)") instead of the expected internal value ("Duration"). The Time/
Duration branches in the if/elif chain never matched, so the rendered
table silently always fell back to priority order regardless of what the
user picked in the "Sort display by" dropdown.
"""

import datetime

import pytest
from streamlit.testing.v1 import AppTest


APP_PATH = "app.py"


def _add_pet(at, name="Jala", age_years=3):
    at.text_input(key="pet_name").set_value(name)
    for n in at.number_input:
        if n.label == "Age (years)":
            n.set_value(age_years)
    for b in at.button:
        if b.label == "Add pet":
            b.click()
    at.run()


def _add_task(at, title, priority, category, hours, minutes, preferred_time=None):
    at.text_input(key="task_title").set_value(title)
    if preferred_time is not None:
        at.checkbox(key="task_no_preferred_time").set_value(False)
        at.run()
        at.time_input(key="task_preferred_time").set_value(preferred_time)
    else:
        at.checkbox(key="task_no_preferred_time").set_value(True)
    for s in at.selectbox:
        if s.label == "Priority":
            s.set_value(priority)
        if s.label == "Category":
            s.set_value(category)
    for n in at.number_input:
        if n.label == "Duration (hours)":
            n.set_value(hours)
        if n.label == "Duration (minutes)":
            n.set_value(minutes)
    for b in at.button:
        if b.label == "Add task":
            b.click()
    at.run()


def _generate_schedule(at, sort_label):
    at.selectbox(key="sort_option").set_value(sort_label)
    for b in at.button:
        if b.label == "Generate schedule":
            b.click()
    at.run()


def _scheduled_task_order(at):
    table = at.table[0].value
    return list(table["Task"])


@pytest.fixture
def app_with_mixed_tasks():
    """App with one pet and three tasks whose priority order, duration order,
    and scheduled-time order are all different from one another:

    - Walks:      high priority,   70 min, scheduled 08:00
    - Groom Hair: medium priority, 10 min, scheduled 09:25
    - Grooming:   medium priority, 126 min, scheduled 09:50
    """
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    _add_pet(at)
    _add_task(at, "Walks", "high", "enrichment", 1, 10, datetime.time(8, 0))
    _add_task(at, "Groom Hair", "medium", "grooming", 0, 10, datetime.time(9, 25))
    _add_task(at, "Grooming", "medium", "grooming", 2, 6, datetime.time(9, 50))

    assert not at.exception
    return at


class TestBuildScheduleSortOptions:
    """End-to-end regression tests driving the real Streamlit app."""

    def test_duration_sort_orders_by_duration_regardless_of_priority(self, app_with_mixed_tasks):
        at = app_with_mixed_tasks
        _generate_schedule(at, "Duration (shortest first)")

        assert not at.exception
        assert _scheduled_task_order(at) == ["Groom Hair", "Walks", "Grooming"]

    def test_priority_sort_orders_high_priority_first(self, app_with_mixed_tasks):
        at = app_with_mixed_tasks
        _generate_schedule(at, "Priority (high → low)")

        assert not at.exception
        assert _scheduled_task_order(at)[0] == "Walks"

    def test_time_sort_orders_by_scheduled_time(self, app_with_mixed_tasks):
        at = app_with_mixed_tasks
        _generate_schedule(at, "Time (earliest first)")

        assert not at.exception
        assert _scheduled_task_order(at) == ["Walks", "Groom Hair", "Grooming"]

    def test_switching_sort_option_changes_table_order(self, app_with_mixed_tasks):
        """Directly guards against the dict-selectbox regression: picking a
        different sort option must actually change the rendered row order."""
        at = app_with_mixed_tasks

        _generate_schedule(at, "Time (earliest first)")
        time_order = _scheduled_task_order(at)

        _generate_schedule(at, "Duration (shortest first)")
        duration_order = _scheduled_task_order(at)

        assert time_order != duration_order
