# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info [Sign up page]
- Let a user add/edit tasks (duration + priority at minimum) 
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## 🏗️ System Overview

PawPal+ is built around four core classes (see [`diagrams/uml.mmd`](diagrams/uml.mmd) for the full UML), all defined in [pawpal_system.py](pawpal_system.py):

- `Owner` holds identifying/contact info, work-hour and break-time constraints, and a list of `Pet`s. It handles task CRUD (`add_task`, `edit_task`, `delete_task`, `mark_task_complete`) and can pull every task across all its pets with `get_all_tasks_across_pets()`.
- `Pet` holds identifying info (name, type, age, gender, color) plus its own list of `Task`s, with `add_task`/`remove_task`/`get_tasks` to manage them.
- `Task` is a single care activity: name, category, duration, priority, frequency, due date, and completion status. It can mark itself complete (`mark_complete()`), check if it's recurring (`is_recurring()`), check if it fits a time slot (`can_fit_in_time_slot()`), and generate its own next occurrence (`calculate_next_due_date()`, `create_next_occurrence()`).
- `Scheduler` operates across all of an owner's pets at once — sorting, filtering, conflict detection, and full daily-schedule generation (see the algorithmic features table below).

An `Owner` has many `Pet`s, each `Pet` has many `Task`s (an `Owner` can also hold owner-level tasks directly), and a `Scheduler` is built around one `Owner` to work across everything it holds.

## 🖥️ Sample Output

Sample CLI output from `python main.py`:

```
============================================================
PawPal+ Daily Schedule for Alice Johnson
Date: Saturday, July 04, 2026
============================================================

Owner: Alice Johnson
Email: alice@example.com
Available Time: 4.0 hours/day

PETS:
  • Max (Dog) - 3 years old, Golden Retriever
  • Whiskers (Cat) - 5 years old, Orange Tabby

TODAY'S SCHEDULE (Prioritized):
------------------------------------------------------------
1. [08:00 - 08:30] Morning Walk (exercise)
   Pet: Max | Duration: 30 min | Priority: high

2. [08:30 - 08:40] Feed Max (feeding)
   Pet: Max | Duration: 10 min | Priority: high

3. [08:40 - 08:45] Feed Whiskers (feeding)
   Pet: Whiskers | Duration: 5 min | Priority: high

4. [08:45 - 09:05] Play with Whiskers (play)
   Pet: Whiskers | Duration: 20 min | Priority: medium

------------------------------------------------------------
Total Scheduled Time: 65 minutes (1.1 hours)
Available Time: 240 minutes (4.0 hours)
============================================================
```

## 🧪 Testing PawPal+

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output (`pytest -v`, 81 tests):

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0
collecting ... collected 81 items

tests/test_app_ui.py::TestBuildScheduleSortOptions::test_priority_sort_orders_high_priority_first PASSED [  2%]
tests/test_edge_cases.py::TestTaskValidation::test_zero_duration_task_allowed PASSED [  6%]
tests/test_edge_cases.py::TestWorkHoursValidation::test_invalid_hour_values_not_allowed PASSED [ 12%]
tests/test_edge_cases.py::TestTaskDataIntegrity::test_pet_id_mismatch_validated PASSED [ 19%]
tests/test_edge_cases.py::TestFrequencyHandling::test_frequency_completely_ignored PASSED [ 27%]
tests/test_edge_cases.py::TestSchedulerMutation::test_scheduler_doesnt_mutate_owner_state PASSED [ 37%]
tests/test_edge_cases.py::TestMonthlyRecurrenceDateMath::test_monthly_recurrence_from_31st_into_28_day_february PASSED [ 39%]
tests/test_edge_cases.py::TestOvernightScheduleHourEqualEdgeCase::test_end_time_after_start_when_hours_equal_but_minutes_earlier PASSED [ 44%]
tests/test_edge_cases.py::TestSortByTimeFormattingEdgeCases::test_sort_by_time_handles_non_zero_padded_hours PASSED [ 45%]
tests/test_edge_cases.py::TestConflictDetectionAdversarial::test_task_fully_nested_inside_another_flagged PASSED [ 51%]
tests/test_pawpal.py::TestTaskCompletion::test_mark_complete_changes_status PASSED [ 61%]
tests/test_pawpal.py::TestOwnerWorkSchedule::test_owner_custom_work_hours PASSED [ 65%]
tests/test_pawpal.py::TestSchedulerWithTimeSlots::test_schedule_respects_priority PASSED [ 74%]
tests/test_pawpal.py::TestRecurrenceLogic::test_completing_daily_task_creates_next_day_occurrence PASSED [ 85%]
tests/test_pawpal.py::TestConflictDetection::test_back_to_back_tasks_are_not_conflicts PASSED [ 88%]
...
============================= 81 passed in 5.37s ==============================
```

**Test coverage summary:**

|          File                 |                                         Focus                                         | Tests |
| ------------------------------| ------------------------------------------------------------------------------------- | ------| 
| `tests/test_pawpal.py`        | Core behavior: task completion, adding tasks to pets, owner work-hour config, `Scheduler.generate_daily_schedule()` (time slots, breaks, work-hour bounds, priority ordering), chronological sorting, recurrence-on-complete, and conflict detection | 24 |
| `tests/test_edge_cases.py`    | Boundary/adversarial cases: zero/negative durations, invalid work hours, overnight schedules (including same-hour rollovers), breaks longer than the work window, invalid/missing/duplicate pet & task IDs, empty schedules, scheduler side effects, month-end recurrence date math, non-zero-padded time sorting, and conflict-detection boundaries (nesting, zero-duration, cross-pet) | 33 |
| `tests/test_app_ui.py`        | Streamlit UI display logic: sort-option behavior in the "Build Schedule" view (priority/time/duration ordering, and that switching the sort option actually changes displayed order) | 4 |

## 📐 Smarter Scheduling

| Feature | Method | Implementation |
|---------|--------|-----------------|
| Sort by priority | `Scheduler.sort_by_priority()` | HIGH → MEDIUM → LOW |
| Sort by duration | `Scheduler.sort_by_duration()` | Shortest first |
| Sort by time | `Scheduler.sort_by_time()` | Earliest scheduled time first; parses `"HH:MM"` into minutes-of-day so non-zero-padded times (e.g. `"9:00"`) still sort correctly, unscheduled tasks last |
| Filter by pet | `Scheduler.filter_by_pet()` | Case-insensitive pet name lookup |
| Filter by status | `Scheduler.filter_by_status()` | Show completed or incomplete tasks |
| Conflict detection | `Scheduler.detect_conflicts()` | Finds overlapping time slots |
| Recurring task generation | `Task.calculate_next_due_date()`, `Task.create_next_occurrence()` | Auto-generates next DAILY/WEEKLY/MONTHLY occurrence; MONTHLY clamps to the last valid day of the target month (e.g. Jan 31 → Feb 28) instead of crashing |
| Auto-complete with recurrence | `Owner.mark_task_complete()` | Marks task done and creates next occurrence |
| Daily schedule generation | `Scheduler.generate_daily_schedule()` | Builds complete daily plan respecting time constraints; overnight schedules (`Owner.get_work_day_end_time()`) correctly roll over to the next day even when start/end share an hour |

## 📸 Demo Walkthrough

Run `python main.py` and you'll see this happen in order:

1. An owner (Alice) and two pets (Max the dog, Whiskers the cat) are created.
2. Four daily tasks are added across the two pets, with different priorities and times.
3. The scheduler builds a prioritized daily schedule that fits the owner's work hours, with breaks between tasks.
4. The schedule is checked for time conflicts — then a second, intentionally overlapping schedule is checked too, to show a conflict actually getting flagged.
5. All tasks are sorted by time, then filtered down to just Max's tasks and just Whiskers' tasks.
6. One task is marked complete, which automatically creates its next daily occurrence.
7. Tasks are filtered into completed vs. incomplete lists.

The sample output above is exactly what this produces.

**Streamlit app**: `app.py` exposes the same `Owner` / `Pet` / `Task` / `Scheduler` classes through a UI — enter owner info and work hours, add pets and tasks, then click "Generate schedule" to see the prioritized plan. Run it with `streamlit run app.py`.
