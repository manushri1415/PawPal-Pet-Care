# PawPal+ Recurring Tasks: Implementation Approaches

## Context
You're adding smart algorithms to PawPal+. Recurring task filtering is priority #1 — it determines which tasks should appear on a given date based on their frequency (DAILY, WEEKLY, MONTHLY, AS_NEEDED, ONCE).

---

## 4 Approaches Compared

### Approach 1: Simple Date-Based (Easiest)
Decide if a task appears today based purely on frequency and date math. No state tracking.

```python
def should_task_appear_on_date(task: Task, target_date: datetime) -> bool:
    if task.frequency == Frequency.ONCE:
        return True
    if task.frequency == Frequency.DAILY:
        return True
    if task.frequency == Frequency.WEEKLY:
        return task.created_date.weekday() == target_date.weekday()
    if task.frequency == Frequency.MONTHLY:
        return task.created_date.day == target_date.day
    if task.frequency == Frequency.AS_NEEDED:
        return False
    return False
```

**Pros:** Simple, no persistence needed, works immediately  
**Cons:** Doesn't know if task was already done today; can't skip a day  
**Best for:** First MVP, no completion tracking yet

---

### Approach 2: Track Completion History (⭐ RECOMMENDED)
Remember when each task was last completed; calculate next occurrence based on frequency.

```python
class Task:
    def __init__(self, ...):
        self.last_completed: Optional[datetime] = None
        # ... other fields ...
    
    def should_appear_on_date(self, target_date: datetime) -> bool:
        """Check if task should appear, respecting last completion."""
        if self.frequency == Frequency.ONCE:
            return not self.completed
        
        if self.frequency == Frequency.DAILY:
            # Skip if already done today
            if self.last_completed:
                return self.last_completed.date() < target_date.date()
            return True
        
        if self.frequency == Frequency.WEEKLY:
            if self.last_completed:
                days_since = (target_date - self.last_completed).days
                return days_since >= 7
            return True
        
        if self.frequency == Frequency.MONTHLY:
            if self.last_completed:
                # Check if enough days have passed
                return (target_date.month, target_date.day) != (self.last_completed.month, self.last_completed.day)
            return True
        
        if self.frequency == Frequency.AS_NEEDED:
            return False
        
        return False
```

**Pros:** Realistic for actual schedules; respects "already done today"  
**Cons:** Requires updating `last_completed` when task is marked complete  
**Best for:** Real-world usage where people actually check off tasks

**What you need to add:**
- Add `last_completed` field to Task.__init__()
- Add `should_appear_on_date()` method to Task
- Update `mark_complete()` to set `last_completed = datetime.now()`
- Call this in `Scheduler.get_tasks_for_date()` to filter tasks

---

### Approach 3: Stored Recurrence Schedule (Most Flexible)
Store explicit day(s) of week in each task. User picks "Mon/Wed/Fri" not just "weekly".

```python
class Task:
    def __init__(self, ...):
        self.recurrence_days: List[int] = []  # [0=Mon, 1=Tue, ..., 6=Sun]
    
    def should_appear_on_date(self, target_date: datetime) -> bool:
        if self.frequency == Frequency.WEEKLY:
            return target_date.weekday() in self.recurrence_days
        # ... handle other frequencies ...
```

UI change needed in `app.py`:
```python
if task.frequency == Frequency.WEEKLY:
    recurrence_days = st.multiselect(
        "Which days of week?",
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        key="recurrence_days"
    )
```

**Pros:** User controls exactly which days; very predictable  
**Cons:** More UI complexity; more data to manage  
**Best for:** Power users who want "walk on Mon/Wed/Fri"

---

### Approach 4: Cron Expressions (Most Powerful)
Use cron-style strings: `"0 9 * * MON"` = every Monday at 9 AM.

```python
from croniter import croniter  # External library needed

class Task:
    def __init__(self, ...):
        self.cron_expression: str = "* * * * *"
    
    def should_appear_on_date(self, target_date: datetime) -> bool:
        cron = croniter(self.cron_expression, self.last_completed or self.created_date)
        return cron.get_next(datetime) <= target_date
```

**Pros:** Extremely flexible; can express complex patterns ("last Friday of month")  
**Cons:** Steep learning curve for users; overkill for pet care  
**Best for:** Advanced power users only

---

## Recommendation: Approach 2 ⭐

**Why:** 
- Realistic for actual pet schedules
- Minimal UI changes
- Respects task completion
- Can expand to Approach 3 later if users ask

**Implementation steps:**
1. Add `last_completed` field to Task class
2. Add `should_appear_on_date(target_date)` method to Task
3. Update `mark_complete()` to set `last_completed`
4. Implement `Scheduler.get_tasks_for_date(date)` to filter using this method
5. Update daily schedule generation to use filtered tasks

---

## Next Steps
1. Decide on approach (recommend #2)
2. Implement the selected approach
3. Test with recurring tasks (daily walk, weekly grooming, etc.)
4. Add UI indicator showing "next occurrence" for recurring tasks
5. Move to Filtering #2 (conflict detection) or other algorithms

---

## Related Code Locations
- **Task class:** `pawpal_system.py:55-96`
- **Scheduler.get_tasks_for_date():** `pawpal_system.py:249-252` (currently just returns all tasks)
- **Scheduler.generate_daily_schedule():** `pawpal_system.py:268-295`
- **UI schedule display:** `app.py:170-200`
