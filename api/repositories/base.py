"""The storage contract the API is written against.

Every read and write the services make goes through an :class:`OwnerRepository`
-- a repository *bound to one owner*. None of its methods takes an owner id,
so there is no way to forget one: a service handed visitor A's repository can
only ever see or change visitor A's pets, tasks, records, reminders, conflicts,
audit entries and document chunks, and a lookup by another owner's object id
simply finds nothing. That binding is the isolation boundary between demo
visitors.

A :class:`StorageBackend` hands out those repositories and manages the owners
themselves: creating one, looking one up to validate a session, wiping one for
a demo reset, and importing the seeded demo snapshot.

Rows come back as plain dicts keyed by column name, with the same value types
from every backend (ISO strings for dates, ints for counters and booleans), so
the services never know which backend they are talking to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from pawpal_ai.health_models import Conflict, HealthRecord, Reminder, ReviewStatus
from pawpal_system import Owner, Pet, Task

Row = dict[str, Any]

KIND_DEMO = "demo"
KIND_OWNER = "owner"

# Tables in a snapshot, in dependency order (owners before the pets that
# reference them, pets before tasks). Every backend exports and imports these.
SNAPSHOT_TABLES = (
    "pets",
    "tasks",
    "documents",
    "records",
    "reminders",
    "conflicts",
    "audit_log",
)


class ForeignOwnerError(PermissionError):
    """A write named an object id that already belongs to a different owner.

    Ids are server-generated and random, so this should be unreachable; it is
    raised rather than silently overwriting the other owner's row.
    """


def utc_now_iso() -> str:
    """Timestamp for created_at/updated_at columns: UTC, explicit offset,
    microseconds -- so rows written in the same second still sort in write
    order, and a browser renders an audit entry in the visitor's own zone."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def default_profile() -> Row:
    """Profile columns for a brand-new owner: the domain's own defaults."""
    owner = Owner(name="Pet Owner")
    return {
        "name": owner.name,
        "email": owner.email,
        "phone_number": owner.phone_number,
        "available_hours_per_day": owner.available_hours_per_day,
        "work_start_hour": owner.work_start_hour,
        "work_start_minute": owner.work_start_minute,
        "work_end_hour": owner.work_end_hour,
        "work_end_minute": owner.work_end_minute,
        "break_between_tasks_minutes": owner.break_between_tasks_minutes,
    }


@dataclass(frozen=True)
class OwnerRecord:
    """What a session check needs to know about an owner."""

    owner_id: str
    kind: str  # KIND_DEMO | KIND_OWNER
    expires_at: Optional[int]  # epoch seconds; None never expires

    def is_expired(self, now_epoch: int) -> bool:
        return self.expires_at is not None and self.expires_at <= now_epoch


class OwnerRepository(Protocol):
    owner_id: str

    # -- profile ------------------------------------------------------------
    def get_profile(self) -> Row: ...
    def update_profile(self, **fields: Any) -> Row: ...

    # -- pets ---------------------------------------------------------------
    def create_pet(self, pet: Pet) -> Row: ...
    def get_pet(self, pet_id: str) -> Optional[Row]: ...
    def list_pets(self) -> list[Row]: ...
    def update_pet(self, pet_id: str, **fields: Any) -> Optional[Row]: ...
    def delete_pet(self, pet_id: str) -> bool:
        """Delete a pet and its tasks. Health records are left in place."""
        ...

    # -- tasks --------------------------------------------------------------
    def create_task(self, task: Task) -> Row: ...
    def get_task(self, task_id: str) -> Optional[Row]: ...
    def list_tasks(self, pet_id: Optional[str] = None) -> list[Row]: ...
    def update_task(self, task_id: str, **fields: Any) -> Optional[Row]: ...
    def delete_task(self, task_id: str) -> bool: ...
    def complete_task(self, task_id: str, next_task: Optional[Task]) -> bool:
        """Atomically mark an open task completed and insert ``next_task``.
        False, writing nothing, when the task is missing or already completed."""
        ...

    # -- documents ----------------------------------------------------------
    def save_document(
        self,
        pet_id: str,
        filename: str,
        doc_type: str,
        char_count: int,
        injection_flagged: bool = False,
        document_id: Optional[str] = None,
    ) -> str: ...

    # -- records ------------------------------------------------------------
    def save_record(self, record: HealthRecord, document_id: str = "") -> str: ...
    def get_record(self, record_id: str) -> Optional[HealthRecord]: ...
    def get_record_document_id(self, record_id: str) -> Optional[str]: ...
    def list_records(
        self, pet_id: str, review_status: Optional[ReviewStatus] = None
    ) -> list[HealthRecord]: ...
    def count_records(self, pet_id: str) -> int: ...
    def set_review_status(self, record_id: str, status: ReviewStatus) -> None: ...

    # -- reminders ----------------------------------------------------------
    def save_reminder(self, reminder: Reminder) -> str: ...
    def list_reminders(self, pet_id: str) -> list[Reminder]: ...

    # -- conflicts ----------------------------------------------------------
    def save_conflict_if_absent(self, conflict: Conflict) -> Optional[str]: ...
    def get_conflict(self, conflict_id: str) -> Optional[Row]: ...
    def list_conflicts(self, pet_id: str, unresolved_only: bool = False) -> list[Row]: ...
    def resolve_conflict(self, conflict_id: str) -> None: ...

    # -- audit --------------------------------------------------------------
    def audit_trail(self, limit: int = 100) -> list[Row]: ...


class StorageBackend(Protocol):
    def for_owner(self, owner: OwnerRecord) -> OwnerRepository: ...

    def get_owner(self, owner_id: str) -> Optional[OwnerRecord]: ...

    def create_owner(self, owner: OwnerRecord, profile: Optional[Row] = None) -> bool:
        """Insert the owner (and its profile) unless it exists. True if created."""
        ...

    def delete_owner(self, owner_id: str) -> None:
        """Remove the owner and every row it owns."""
        ...

    def import_snapshot(self, owner: OwnerRecord, snapshot: dict[str, Any]) -> None:
        """Create ``owner`` with the profile and rows in ``snapshot``."""
        ...

    def export_snapshot(self, owner_id: str) -> dict[str, Any]: ...

    def purge_expired(self, now_epoch: int, limit: int = 50) -> int:
        """Delete up to ``limit`` expired demo owners; return how many."""
        ...

    def close(self) -> None: ...
