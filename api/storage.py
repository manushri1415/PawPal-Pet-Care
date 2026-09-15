"""SQLite persistence for the scheduler domain (owners/pets/tasks).

Same physical file as pawpal_ai's ``data/pawpal.db``, but a separate
connection and schema — pawpal_ai/storage.py is never touched from here.
Follows the same thin-repository-over-stdlib-sqlite3 style (see
pawpal_ai/storage.py): plain columns for what's queried on, no ORM.

This is the one genuinely new backend subsystem in the migration — before
this, pawpal_system.py's Owner/Pet/Task graph lived only in Streamlit
``st.session_state`` with zero persistence.
"""

from __future__ import annotations

import functools
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from pawpal_system import Owner, Pet, Task

_F = TypeVar("_F", bound=Callable[..., Any])


def _locked(method: _F) -> _F:
    """Serialize access to ``self._conn``.

    FastAPI runs each request's sync dependencies/handlers in its own
    threadpool thread, but ``get_scheduler_storage()`` (api/deps.py) hands
    every request the *same* process-wide ``SchedulerStorage`` instance --
    and therefore the same single ``sqlite3.Connection`` (opened with
    ``check_same_thread=False`` so cross-thread use doesn't raise outright).
    Two requests landing in the same instant can then interleave statements
    on that one connection/cursor, which surfaced during Phase 4's browser
    smoke test as an intermittent, spurious 404 from a `get_pet` that ran
    concurrently with another request's write -- the pet was never actually
    missing. A single ``RLock`` around every method that touches the
    connection serializes access (reentrant so e.g. ``update_owner`` calling
    ``get_or_create_owner`` doesn't deadlock itself); a single-file SQLite
    demo app has no throughput need for finer-grained locking.
    """

    @functools.wraps(method)
    def wrapper(self: "SchedulerStorage", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS owners (
    owner_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    phone_number TEXT,
    available_hours_per_day REAL NOT NULL,
    work_start_hour INTEGER NOT NULL,
    work_start_minute INTEGER NOT NULL,
    work_end_hour INTEGER NOT NULL,
    work_end_minute INTEGER NOT NULL,
    break_between_tasks_minutes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pets (
    pet_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(owner_id),
    name TEXT NOT NULL,
    pet_type TEXT NOT NULL,
    age INTEGER NOT NULL,
    age_months INTEGER NOT NULL DEFAULT 0,
    gender TEXT NOT NULL,
    color TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(owner_id),
    pet_id TEXT REFERENCES pets(pet_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    duration INTEGER NOT NULL,
    priority TEXT NOT NULL,
    frequency TEXT NOT NULL,
    notes TEXT,
    scheduled_time TEXT,
    due_date TEXT NOT NULL,
    end_date TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Owner is a singleton row -- /api/owner never takes an id (see MIGRATION_PLAN.md §2).
_SINGLETON_OWNER_ID = "owner"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SchedulerStorage:
    """Repository over the owners/pets/tasks tables in ``data/pawpal.db``."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # Serializes every method below (see _locked) -- necessary because
        # this instance is a process-wide singleton shared across FastAPI's
        # per-request threadpool threads, not just a thread-hop guard.
        self._lock = threading.RLock()
        # check_same_thread=False: FastAPI's TestClient/uvicorn may hop
        # threads; this connection is only ever driven through SchedulerService.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Own connection into the same file pawpal_ai/storage.py writes to --
        # these three pragmas make sharing that file safe: FK enforcement
        # (SQLite defaults it off per-connection), WAL so this connection's
        # reads don't block pawpal_ai's writer (or vice versa), and a
        # busy_timeout so a momentary lock retries instead of raising
        # "database is locked".
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- owner (singleton) ---------------------------------------------------
    @_locked
    def get_or_create_owner(self) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM owners WHERE owner_id=?", (_SINGLETON_OWNER_ID,)
        ).fetchone()
        if row is not None:
            return row

        default = Owner(name="Pet Owner")
        now = _now()
        self._conn.execute(
            "INSERT INTO owners(owner_id, name, email, phone_number, available_hours_per_day,"
            " work_start_hour, work_start_minute, work_end_hour, work_end_minute,"
            " break_between_tasks_minutes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                _SINGLETON_OWNER_ID, default.name, default.email, default.phone_number,
                default.available_hours_per_day, default.work_start_hour, default.work_start_minute,
                default.work_end_hour, default.work_end_minute, default.break_between_tasks_minutes,
                now, now,
            ),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT * FROM owners WHERE owner_id=?", (_SINGLETON_OWNER_ID,)
        ).fetchone()

    @_locked
    def update_owner(self, **fields: Any) -> sqlite3.Row:
        self.get_or_create_owner()  # ensure the row exists first
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            self._conn.execute(
                f"UPDATE owners SET {set_clause}, updated_at=? WHERE owner_id=?",
                (*fields.values(), _now(), _SINGLETON_OWNER_ID),
            )
            self._conn.commit()
        return self.get_or_create_owner()

    # -- pets ------------------------------------------------------------------
    @_locked
    def create_pet(self, pet: Pet, owner_id: str = _SINGLETON_OWNER_ID) -> sqlite3.Row:
        now = _now()
        self._conn.execute(
            "INSERT INTO pets(pet_id, owner_id, name, pet_type, age, age_months, gender, color,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                pet.id, owner_id, pet.name, pet.type, pet.age, pet.age_months, pet.gender.value,
                pet.color, now, now,
            ),
        )
        self._conn.commit()
        return self.get_pet(pet.id)

    @_locked
    def get_pet(self, pet_id: str) -> Optional[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM pets WHERE pet_id=?", (pet_id,)).fetchone()

    @_locked
    def list_pets(self, owner_id: str = _SINGLETON_OWNER_ID) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM pets WHERE owner_id=? ORDER BY created_at", (owner_id,)
        ).fetchall()

    @_locked
    def update_pet(self, pet_id: str, **fields: Any) -> Optional[sqlite3.Row]:
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            self._conn.execute(
                f"UPDATE pets SET {set_clause}, updated_at=? WHERE pet_id=?",
                (*fields.values(), _now(), pet_id),
            )
            self._conn.commit()
        return self.get_pet(pet_id)

    @_locked
    def delete_pet(self, pet_id: str) -> bool:
        # tasks.pet_id has ON DELETE CASCADE, so this also removes the pet's tasks
        # -- matching today's in-memory behavior (once a pet leaves owner.pets,
        # its tasks are unreachable from get_all_tasks_across_pets() too).
        cur = self._conn.execute("DELETE FROM pets WHERE pet_id=?", (pet_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # -- tasks -------------------------------------------------------------------
    def _insert_task(self, task: Task, owner_id: str, now: str) -> None:
        """INSERT one task row without committing -- callers own the transaction."""
        self._conn.execute(
            "INSERT INTO tasks(task_id, owner_id, pet_id, name, category, duration, priority,"
            " frequency, notes, scheduled_time, due_date, end_date, completed, created_at,"
            " updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                task.id, owner_id, task.pet_id or None, task.name, task.category.value,
                task.duration, task.priority.value, task.frequency.value, task.notes,
                task.scheduled_time, task.due_date.isoformat(),
                task.end_date.isoformat() if task.end_date else None,
                int(task.completed), now, now,
            ),
        )

    @_locked
    def create_task(self, task: Task, owner_id: str = _SINGLETON_OWNER_ID) -> sqlite3.Row:
        self._insert_task(task, owner_id, _now())
        self._conn.commit()
        return self.get_task(task.id)

    @_locked
    def get_task(self, task_id: str) -> Optional[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()

    @_locked
    def list_tasks(
        self, owner_id: str = _SINGLETON_OWNER_ID, pet_id: Optional[str] = None
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM tasks WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if pet_id is not None:
            query += " AND pet_id=?"
            params.append(pet_id)
        query += " ORDER BY created_at"
        return self._conn.execute(query, params).fetchall()

    @_locked
    def update_task(self, task_id: str, **fields: Any) -> Optional[sqlite3.Row]:
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            self._conn.execute(
                f"UPDATE tasks SET {set_clause}, updated_at=? WHERE task_id=?",
                (*fields.values(), _now(), task_id),
            )
            self._conn.commit()
        return self.get_task(task_id)

    @_locked
    def delete_task(self, task_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
        self._conn.commit()
        return cur.rowcount > 0

    @_locked
    def complete_task(
        self, task_id: str, next_task: Optional[Task], owner_id: str = _SINGLETON_OWNER_ID
    ) -> bool:
        """Mark a task completed and, in the same transaction, insert the
        recurring task's next occurrence.

        Returns False -- writing nothing -- if the task is missing or already
        completed. The UPDATE is conditional on ``completed=0``, so of two
        requests completing the same task at once exactly one sees a changed
        row and only that one inserts ``next_task``; a double-click can no
        longer leave two copies of tomorrow's walk. The insert happens only
        after that check and commits together with it, so a failure between
        the two cannot leave the task completed with its next occurrence lost.
        """
        now = _now()
        try:
            cur = self._conn.execute(
                "UPDATE tasks SET completed=1, updated_at=? WHERE task_id=? AND completed=0",
                (now, task_id),
            )
            if cur.rowcount == 0:
                self._conn.rollback()
                return False
            if next_task is not None:
                self._insert_task(next_task, owner_id, now)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return True


def init_db(db_path: str | Path) -> SchedulerStorage:
    """Create (if needed) and return a SchedulerStorage handle for ``db_path``."""
    return SchedulerStorage(db_path)
