"""The seeded demo sandbox every new visitor session starts from.

``seed.json`` beside this module is a snapshot of one owner's data produced by
running the real PawPal services -- pets and routine through the scheduler,
fixture-derived vet documents through the real extraction pipeline, human
approvals, schedule-care -- see scripts/build_demo_seed.py. Replaying a
snapshot costs a single batch write, where re-running the pipeline would put
every document's extraction in front of a visitor's first page load.

Two rewrites make each copy a fresh, private, current sandbox:

- **Ids.** Every object id in the snapshot is replaced with a newly generated
  one of the same shape, and every reference to it (a record's document_id, a
  chunk id, an evidence citation, a reminder's ``rem_<record_id>``) follows,
  because the rewrite is done on the serialized text. No two sessions share an
  id, so knowing the demo's ids from one sandbox tells you nothing about
  another's.
- **Dates.** Every ISO date is moved by the distance between the snapshot's
  anchor date and the visitor's today, so "due in 20 days" stays due in 20
  days whichever day the sandbox is created -- in the field, in the source
  text quoted as evidence, and in the reminder. Reminder care statuses are then
  recomputed for that today.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pawpal_ai.reminders import compute_care_status
from pawpal_ai.storage import conflict_id_for

from api.repositories.base import OwnerRecord, StorageBackend
from api.repositories.rows import row_to_conflict

SEED_PATH = Path(__file__).with_name("seed.json")

_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _hex(prefix: str, length: int):
    return lambda: f"{prefix}_{uuid.uuid4().hex[:length]}"


# (snapshot table, id column, generator of a new id with the same shape).
_ID_COLUMNS = (
    ("pets", "pet_id", _new_uuid),
    ("tasks", "task_id", _new_uuid),
    ("documents", "document_id", None),  # shape copied from the old id below
    ("records", "record_id", None),
    ("audit_log", "id", None),
)


def _same_shape_id(old: str) -> str:
    """A fresh id shaped like ``old``: a uuid for a uuid, else ``prefix_<hex>``
    with the same prefix and hex length."""
    try:
        uuid.UUID(old)
        return _new_uuid()
    except ValueError:
        prefix, _, tail = old.rpartition("_")
        return f"{prefix}_{uuid.uuid4().hex[: len(tail)]}"


class DemoSeeder:
    def __init__(self, snapshot: dict[str, Any]):
        self._anchor = date.fromisoformat(snapshot["anchor_date"])
        self._text = json.dumps(snapshot["data"], sort_keys=True)
        data = snapshot["data"]
        self._ids = [row[col] for table, col, _ in _ID_COLUMNS for row in data.get(table, [])]

    def build(self, today: date) -> dict[str, Any]:
        """A fresh copy of the snapshot: new ids, dates moved to ``today``."""
        mapping = {old: _same_shape_id(old) for old in self._ids}
        text = self._text
        if mapping:
            # Longest first, so no id can match inside a longer one.
            pattern = re.compile("|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)))
            text = pattern.sub(lambda m: mapping[m.group(0)], text)

        shift = today - self._anchor

        def move(m: re.Match) -> str:
            try:
                moved = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) + shift
            except ValueError:
                return m.group(0)
            return moved.isoformat()

        data = json.loads(_ISO_DATE_RE.sub(move, text))

        # Conflict ids are derived from the conflicting values (see
        # pawpal_ai.storage.conflict_id_for), which the rewrite just changed.
        for row in data.get("conflicts", []):
            new_id = conflict_id_for(row_to_conflict(row))
            for audit in data.get("audit_log", []):
                if audit["ref_id"] == row["conflict_id"]:
                    audit["ref_id"] = new_id
            row["conflict_id"] = new_id

        for row in data.get("reminders", []):
            row["care_status"] = compute_care_status(date.fromisoformat(row["due_date"]), today).value
        return data

    def seed(self, backend: StorageBackend, owner: OwnerRecord, today: date) -> None:
        backend.import_snapshot(owner, self.build(today))


@lru_cache
def load_default_seeder() -> Optional[DemoSeeder]:
    if not SEED_PATH.is_file():
        return None
    return DemoSeeder(json.loads(SEED_PATH.read_text(encoding="utf-8")))
