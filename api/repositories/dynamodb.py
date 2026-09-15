"""DynamoDB storage backend -- production on AWS.

**One table, one partition per owner.** Every item's partition key is
``OWNER#{owner_id}``; the sort key says what it is::

    PROFILE                              the owner row: routine settings, kind, expiry
    PET#{pet_id}
    TASK#{task_id}
    DOC#{document_id}                    document metadata (never the file itself)
    CHUNK#{document_id}#{seq:05d}        retrieval chunk text, in document order
    REC#{record_id}
    REM#{reminder_id}
    CFT#{conflict_id}
    AUDIT#{created_at}#{id}              sorts chronologically

Every access pattern the services have is "this owner's X" or "this owner's X
with this id", so every read is a ``GetItem`` on a full key or a ``Query`` on
the owner's partition with a sort-key prefix -- no scans, and no secondary
index. The owner id is part of every key, so another owner's object cannot be
fetched by id: the key names a different partition. Per-pet filtering happens
inside the owner's partition, which holds a demo's worth of items.

**Consistency.** Every read is strongly consistent. The UI refetches right
after each mutation (complete a task, then list tasks), and an eventually
consistent read there can show the state from before the click. For a
partition this size the cost is a rounding error.

**Atomicity.** Completing a task is one ``TransactWriteItems``: the update is
conditional on the task still being open, and the next occurrence is put in
the same transaction -- the DynamoDB form of SQLite's conditional UPDATE plus
INSERT. A mutation and its audit entry are written together the same way, and
a conflict is inserted with ``attribute_not_exists`` on its deterministic id.

**Expiry.** Items of a demo owner carry ``expires_at`` (epoch seconds), the
table's TTL attribute, so DynamoDB deletes an abandoned sandbox on its own.
TTL deletion can lag by days, so it is only cleanup: api/sessions.py checks the
profile's ``expires_at`` on every request. The owner space's items carry no
``expires_at`` and are never expired.

Numbers come back from DynamoDB as ``Decimal``; rows are converted to the same
ints and floats the SQLite backend returns (api/repositories/rows.py).
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any, Iterable, Optional

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.config import Config
from botocore.exceptions import ClientError

from pawpal_ai.health_models import Conflict, HealthRecord, Reminder, ReviewStatus
from pawpal_ai.logging_setup import log_event
from pawpal_ai.storage import conflict_id_for
from pawpal_ai.vectorstore import Chunk
from pawpal_system import Pet, Task

from api.repositories.base import (
    SNAPSHOT_TABLES,
    OwnerRecord,
    Row,
    default_profile,
    utc_now_iso,
)
from api.repositories.rows import (
    chunk_to_row,
    conflict_to_row,
    pet_to_row,
    record_to_row,
    reminder_to_row,
    row_to_chunk,
    row_to_record,
    row_to_reminder,
    task_to_row,
)

TTL_ATTRIBUTE = "expires_at"
PROFILE_SK = "PROFILE"

_PREFIX = {
    "pets": "PET#",
    "tasks": "TASK#",
    "documents": "DOC#",
    "chunks": "CHUNK#",
    "records": "REC#",
    "reminders": "REM#",
    "conflicts": "CFT#",
    "audit_log": "AUDIT#",
}
_ID_COLUMN = {
    "pets": "pet_id",
    "tasks": "task_id",
    "documents": "document_id",
    "records": "record_id",
    "reminders": "reminder_id",
    "conflicts": "conflict_id",
    "audit_log": "id",
    "chunks": "seq",
}
_INT_COLUMNS = frozenset({
    "age", "age_months", "duration", "completed", "char_count", "injection_flagged", "resolved", "seq",
    "work_start_hour", "work_start_minute", "work_end_hour", "work_end_minute",
    "break_between_tasks_minutes", TTL_ATTRIBUTE,
})
_FLOAT_COLUMNS = frozenset({"available_hours_per_day", "confidence"})
_PROFILE_COLUMNS = tuple(default_profile())

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()

# BatchWriteItem's per-request ceiling.
_BATCH_SIZE = 25


def _pk(owner_id: str) -> str:
    return f"OWNER#{owner_id}"


def _sk(table: str, row: Row) -> str:
    if table == "chunks":
        return f"CHUNK#{row['document_id']}#{int(row['seq']):05d}"
    if table == "audit_log":
        return f"AUDIT#{row['created_at']}#{row['id']}"
    return _PREFIX[table] + row[_ID_COLUMN[table]]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(repr(value))
    return value


def _serialize(values: dict[str, Any]) -> dict[str, Any]:
    return {k: _serializer.serialize(_to_dynamo(v)) for k, v in values.items()}


def _from_dynamo(name: str, value: Any) -> Any:
    if isinstance(value, Decimal):
        if name in _FLOAT_COLUMNS:
            return float(value)
        if name in _INT_COLUMNS or value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def _deserialize(item: dict[str, Any]) -> Row:
    return {k: _from_dynamo(k, _deserializer.deserialize(v)) for k, v in item.items()}


def _strip(item: Row, keep_expiry: bool = False) -> Row:
    out = {k: v for k, v in item.items() if k not in ("PK", "SK")}
    if not keep_expiry:
        out.pop(TTL_ATTRIBUTE, None)
    return out


def _is_condition_failure(err: ClientError) -> bool:
    error = err.response.get("Error", {})
    code = error.get("Code", "")
    if code == "ConditionalCheckFailedException":
        return True
    if code == "TransactionCanceledException":
        reasons = err.response.get("CancellationReasons") or []
        if any(r.get("Code") == "ConditionalCheckFailed" for r in reasons):
            return True
        return "ConditionalCheckFailed" in error.get("Message", "")
    return False


def create_table(client: Any, table_name: str) -> None:
    """Create the table as infra/template.yaml defines it -- for tests and a
    local DynamoDB. Production gets its table from CloudFormation."""
    client.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name)
    client.update_time_to_live(
        TableName=table_name,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
    )


class DynamoBackend:
    """:class:`~api.repositories.base.StorageBackend` over one DynamoDB table."""

    def __init__(
        self,
        table_name: str,
        client: Any = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        self.table_name = table_name
        # botocore clients are thread-safe; one per process serves every request.
        self._client = client or boto3.client(
            "dynamodb",
            region_name=region_name,
            endpoint_url=endpoint_url,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=3, read_timeout=5),
        )

    def close(self) -> None:
        """Nothing to release: the client holds no per-request state."""

    # -- low-level helpers ------------------------------------------------------
    def _key(self, pk: str, sk: str) -> dict[str, Any]:
        return _serialize({"PK": pk, "SK": sk})

    def _get(self, pk: str, sk: str) -> Optional[Row]:
        resp = self._client.get_item(TableName=self.table_name, Key=self._key(pk, sk), ConsistentRead=True)
        item = resp.get("Item")
        return _deserialize(item) if item else None

    def _query(
        self,
        pk: str,
        prefix: Optional[str] = None,
        *,
        filters: Optional[dict[str, Any]] = None,
        descending: bool = False,
        limit: Optional[int] = None,
        keys_only: bool = False,
    ) -> list[Row]:
        names = {"#pk": "PK"}
        values: dict[str, Any] = {":pk": pk}
        condition = "#pk = :pk"
        if prefix:
            names["#sk"] = "SK"
            values[":prefix"] = prefix
            condition += " AND begins_with(#sk, :prefix)"
        kwargs: dict[str, Any] = {
            "TableName": self.table_name,
            "KeyConditionExpression": condition,
            "ConsistentRead": True,
            "ScanIndexForward": not descending,
        }
        if filters:
            clauses = []
            for i, (name, value) in enumerate(filters.items()):
                names[f"#f{i}"] = name
                values[f":f{i}"] = value
                clauses.append(f"#f{i} = :f{i}")
            kwargs["FilterExpression"] = " AND ".join(clauses)
        if keys_only:
            kwargs["ProjectionExpression"] = "#pk, #sk2"
            names["#sk2"] = "SK"
        kwargs["ExpressionAttributeNames"] = names
        kwargs["ExpressionAttributeValues"] = _serialize(values)

        out: list[Row] = []
        while True:
            if limit is not None and not filters:
                kwargs["Limit"] = limit - len(out)
            resp = self._client.query(**kwargs)
            out.extend(_deserialize(item) for item in resp.get("Items", []))
            if limit is not None and len(out) >= limit:
                return out[:limit]
            last = resp.get("LastEvaluatedKey")
            if not last:
                return out
            kwargs["ExclusiveStartKey"] = last

    def _batch_write(self, requests: list[dict[str, Any]]) -> None:
        for start in range(0, len(requests), _BATCH_SIZE):
            pending = {self.table_name: requests[start : start + _BATCH_SIZE]}
            for attempt in range(8):
                resp = self._client.batch_write_item(RequestItems=pending)
                pending = resp.get("UnprocessedItems") or {}
                if not pending:
                    break
                time.sleep(min(0.05 * 2**attempt, 1.0))
            else:
                raise RuntimeError("DynamoDB kept returning unprocessed items")

    def _put_items(self, items: Iterable[Row]) -> None:
        self._batch_write([{"PutRequest": {"Item": _serialize(item)}} for item in items])

    def _transact(self, operations: list[dict[str, Any]]) -> bool:
        """Run a TransactWriteItems; False if a condition failed (nothing written)."""
        try:
            self._client.transact_write_items(TransactItems=operations)
        except ClientError as err:
            if _is_condition_failure(err):
                return False
            raise
        return True

    def _profile_item(self, owner: OwnerRecord, profile: Row, created_at: Optional[str] = None) -> Row:
        now = utc_now_iso()
        merged = {**default_profile(), **{k: v for k, v in profile.items() if k in _PROFILE_COLUMNS}}
        item = {
            "PK": _pk(owner.owner_id),
            "SK": PROFILE_SK,
            "owner_id": owner.owner_id,
            "kind": owner.kind,
            **merged,
            "created_at": created_at or now,
            "updated_at": now,
        }
        if owner.expires_at is not None:
            item[TTL_ATTRIBUTE] = owner.expires_at
        return item

    def _put_profile_if_absent(self, owner: OwnerRecord, profile: Row, created_at: Optional[str] = None) -> bool:
        try:
            self._client.put_item(
                TableName=self.table_name,
                Item=_serialize(self._profile_item(owner, profile, created_at)),
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as err:
            if _is_condition_failure(err):
                return False
            raise
        return True

    # -- owners ---------------------------------------------------------------------
    def for_owner(self, owner: OwnerRecord) -> "DynamoOwnerRepository":
        return DynamoOwnerRepository(self, owner)

    def get_owner(self, owner_id: str) -> Optional[OwnerRecord]:
        item = self._get(_pk(owner_id), PROFILE_SK)
        if item is None:
            return None
        return OwnerRecord(owner_id=item["owner_id"], kind=item["kind"], expires_at=item.get(TTL_ATTRIBUTE))

    def create_owner(self, owner: OwnerRecord, profile: Optional[Row] = None) -> bool:
        return self._put_profile_if_absent(owner, profile or {})

    def delete_owner(self, owner_id: str) -> None:
        keys = self._query(_pk(owner_id), keys_only=True)
        # The profile goes last: until then a concurrent request still finds
        # the session rather than mistaking a half-deleted one for none.
        keys.sort(key=lambda k: k["SK"] == PROFILE_SK)
        self._batch_write([{"DeleteRequest": {"Key": self._key(k["PK"], k["SK"])}} for k in keys])

    def purge_expired(self, now_epoch: int, limit: int = 50) -> int:
        """No-op: the table's TTL deletes expired demo items. Sessions are
        still checked against expires_at on every request."""
        return 0

    def import_snapshot(self, owner: OwnerRecord, snapshot: dict[str, Any]) -> None:
        profile = snapshot.get("profile") or {}
        if not self._put_profile_if_absent(owner, profile, created_at=profile.get("created_at")):
            raise ValueError(f"owner {owner.owner_id!r} already exists")
        repo = self.for_owner(owner)
        items = [repo._item(table, row) for table in SNAPSHOT_TABLES for row in snapshot.get(table, [])]
        self._put_items(items)

    def export_snapshot(self, owner_id: str) -> dict[str, Any]:
        out: dict[str, Any] = {"profile": None, **{table: [] for table in SNAPSHOT_TABLES}}
        table_by_prefix = {prefix: table for table, prefix in _PREFIX.items()}
        for item in self._query(_pk(owner_id)):
            if item["SK"] == PROFILE_SK:
                out["profile"] = {k: item[k] for k in (*_PROFILE_COLUMNS, "created_at")}
                continue
            prefix = item["SK"].split("#", 1)[0] + "#"
            row = _strip(item)
            row.pop("owner_id", None)
            out[table_by_prefix[prefix]].append(row)
        for table in SNAPSHOT_TABLES:
            key = _ID_COLUMN[table]
            out[table].sort(key=lambda r: (r["created_at"], r[key]))
        return out


class DynamoOwnerRepository:
    """:class:`~api.repositories.base.OwnerRepository` for one owner's partition."""

    def __init__(self, backend: DynamoBackend, owner: OwnerRecord):
        self._b = backend
        self._owner = owner
        self.owner_id = owner.owner_id
        self._pk = _pk(owner.owner_id)

    # -- item construction ----------------------------------------------------------
    def _item(self, table: str, row: Row) -> Row:
        item = {**row, "owner_id": self.owner_id, "PK": self._pk, "SK": _sk(table, row)}
        if self._owner.expires_at is not None:
            item[TTL_ATTRIBUTE] = self._owner.expires_at
        return item

    def _put_op(self, table: str, row: Row, condition: Optional[str] = None) -> dict[str, Any]:
        put: dict[str, Any] = {"TableName": self._b.table_name, "Item": _serialize(self._item(table, row))}
        if condition:
            put["ConditionExpression"] = condition
        return {"Put": put}

    def _audit_op(self, event: str, ref_id: str, detail: str = "") -> dict[str, Any]:
        row = {"id": _new_id("audit"), "event": event, "ref_id": ref_id, "detail": detail, "created_at": utc_now_iso()}
        return self._put_op("audit_log", row)

    def _update(self, sk: str, fields: dict[str, Any], *, touch: bool) -> bool:
        """SET ``fields`` on an existing item; False if there is no such item."""
        if touch:
            fields = {**fields, "updated_at": utc_now_iso()}
        names, values, sets = {}, {}, []
        for i, (name, value) in enumerate(fields.items()):
            names[f"#u{i}"] = name
            values[f":u{i}"] = value
            sets.append(f"#u{i} = :u{i}")
        try:
            self._b._client.update_item(
                TableName=self._b.table_name,
                Key=self._b._key(self._pk, sk),
                UpdateExpression="SET " + ", ".join(sets),
                ConditionExpression="attribute_exists(SK)",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=_serialize(values),
            )
        except ClientError as err:
            if _is_condition_failure(err):
                return False
            raise
        return True

    def _update_op(self, sk: str, fields: dict[str, Any]) -> dict[str, Any]:
        names, values, sets = {}, {}, []
        for i, (name, value) in enumerate(fields.items()):
            names[f"#u{i}"] = name
            values[f":u{i}"] = value
            sets.append(f"#u{i} = :u{i}")
        return {
            "Update": {
                "TableName": self._b.table_name,
                "Key": self._b._key(self._pk, sk),
                "UpdateExpression": "SET " + ", ".join(sets),
                "ConditionExpression": "attribute_exists(SK)",
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": _serialize(values),
            }
        }

    def _row(self, sk: str) -> Optional[Row]:
        item = self._b._get(self._pk, sk)
        return _strip(item) if item else None

    def _rows(self, table: str, prefix: Optional[str] = None, **filters: Any) -> list[Row]:
        items = self._b._query(self._pk, prefix or _PREFIX[table], filters=filters or None)
        return [_strip(item) for item in items]

    # -- profile ---------------------------------------------------------------------
    def get_profile(self) -> Row:
        item = self._b._get(self._pk, PROFILE_SK)
        if item is None:
            # Removed mid-request by a reset or expiry; recreate as sqlite.py does.
            self._b._put_profile_if_absent(self._owner, {})
            item = self._b._get(self._pk, PROFILE_SK)
        row = _strip(item, keep_expiry=True)  # type: ignore[arg-type]
        row.setdefault(TTL_ATTRIBUTE, None)
        return row

    def update_profile(self, **fields: Any) -> Row:
        self.get_profile()
        fields = {k: v for k, v in fields.items() if k in _PROFILE_COLUMNS}
        if fields:
            self._update(PROFILE_SK, fields, touch=True)
        return self.get_profile()

    # -- pets ------------------------------------------------------------------------
    def create_pet(self, pet: Pet) -> Row:
        now = utc_now_iso()
        row = {**pet_to_row(pet), "created_at": now, "updated_at": now}
        self._b._put_items([self._item("pets", row)])
        return self.get_pet(pet.id)  # type: ignore[return-value]

    def get_pet(self, pet_id: str) -> Optional[Row]:
        return self._row(f"PET#{pet_id}")

    def list_pets(self) -> list[Row]:
        return sorted(self._rows("pets"), key=lambda r: r["created_at"])

    def update_pet(self, pet_id: str, **fields: Any) -> Optional[Row]:
        if fields and not self._update(f"PET#{pet_id}", fields, touch=True):
            return None
        return self.get_pet(pet_id)

    def delete_pet(self, pet_id: str) -> bool:
        if self.get_pet(pet_id) is None:
            return False
        # Tasks first: a failure part-way leaves a pet without tasks, never
        # tasks pointing at a pet that is gone.
        doomed = [t for t in self._rows("tasks") if t.get("pet_id") == pet_id]
        requests = [{"DeleteRequest": {"Key": self._b._key(self._pk, f"TASK#{t['task_id']}")}} for t in doomed]
        requests.append({"DeleteRequest": {"Key": self._b._key(self._pk, f"PET#{pet_id}")}})
        self._b._batch_write(requests)
        return True

    # -- tasks -----------------------------------------------------------------------
    def create_task(self, task: Task) -> Row:
        now = utc_now_iso()
        self._b._put_items([self._item("tasks", {**task_to_row(task), "created_at": now, "updated_at": now})])
        return self.get_task(task.id)  # type: ignore[return-value]

    def get_task(self, task_id: str) -> Optional[Row]:
        return self._row(f"TASK#{task_id}")

    def list_tasks(self, pet_id: Optional[str] = None) -> list[Row]:
        rows = self._rows("tasks")
        if pet_id is not None:
            rows = [r for r in rows if r.get("pet_id") == pet_id]
        return sorted(rows, key=lambda r: r["created_at"])

    def update_task(self, task_id: str, **fields: Any) -> Optional[Row]:
        if fields and not self._update(f"TASK#{task_id}", fields, touch=True):
            return None
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        resp = self._b._client.delete_item(
            TableName=self._b.table_name, Key=self._b._key(self._pk, f"TASK#{task_id}"), ReturnValues="ALL_OLD"
        )
        return bool(resp.get("Attributes"))

    def complete_task(self, task_id: str, next_task: Optional[Task]) -> bool:
        now = utc_now_iso()
        complete = {
            "Update": {
                "TableName": self._b.table_name,
                "Key": self._b._key(self._pk, f"TASK#{task_id}"),
                "UpdateExpression": "SET #completed = :one, #updated = :now",
                "ConditionExpression": "attribute_exists(SK) AND #completed = :zero",
                "ExpressionAttributeNames": {"#completed": "completed", "#updated": "updated_at"},
                "ExpressionAttributeValues": _serialize({":one": 1, ":zero": 0, ":now": now}),
            }
        }
        operations = [complete]
        if next_task is not None:
            row = {**task_to_row(next_task), "created_at": now, "updated_at": now}
            operations.append(self._put_op("tasks", row, condition="attribute_not_exists(SK)"))
        return self._b._transact(operations)

    # -- documents & chunks -----------------------------------------------------------------
    def save_document(
        self,
        pet_id: str,
        filename: str,
        doc_type: str,
        char_count: int,
        injection_flagged: bool = False,
        document_id: Optional[str] = None,
    ) -> str:
        document_id = document_id or _new_id("doc")
        row = {
            "document_id": document_id,
            "pet_id": pet_id,
            "filename": filename,
            "doc_type": doc_type,
            "char_count": char_count,
            "injection_flagged": int(injection_flagged),
            "created_at": utc_now_iso(),
        }
        self._b._transact([self._put_op("documents", row), self._audit_op("document_saved", document_id, doc_type)])
        log_event("record_saved", kind="document", document_id=document_id, chars=char_count)
        return document_id

    def save_chunks(self, chunks: list[Chunk]) -> None:
        now = utc_now_iso()
        self._b._put_items(
            self._item("chunks", {**chunk_to_row(chunk, seq), "created_at": now}) for seq, chunk in enumerate(chunks)
        )

    def list_chunks(self, pet_id: str, document_id: Optional[str] = None) -> list[Chunk]:
        prefix = f"CHUNK#{document_id}#" if document_id is not None else "CHUNK#"
        rows = self._rows("chunks", prefix, pet_id=pet_id)
        rows.sort(key=lambda r: (r["created_at"], r["seq"]))
        return [row_to_chunk(r) for r in rows]

    # -- records -----------------------------------------------------------------------------
    def save_record(self, record: HealthRecord, document_id: str = "") -> str:
        record.record_id = record.record_id or _new_id("rec")
        row = {**record_to_row(record, document_id), "created_at": utc_now_iso()}
        self._b._transact(
            [self._put_op("records", row), self._audit_op("record_saved", record.record_id, record.review_status.value)]
        )
        log_event(
            "record_saved",
            kind="record",
            record_id=record.record_id,
            record_type=record.record_type.value,
            review_status=record.review_status.value,
        )
        return record.record_id

    def get_record(self, record_id: str) -> Optional[HealthRecord]:
        row = self._row(f"REC#{record_id}")
        return row_to_record(row) if row else None

    def get_record_document_id(self, record_id: str) -> Optional[str]:
        row = self._row(f"REC#{record_id}")
        return None if row is None else (row.get("document_id") or "")

    def list_records(self, pet_id: str, review_status: Optional[ReviewStatus] = None) -> list[HealthRecord]:
        filters: dict[str, Any] = {"pet_id": pet_id}
        if review_status is not None:
            filters["review_status"] = review_status.value
        rows = sorted(self._rows("records", **filters), key=lambda r: r["created_at"])
        return [row_to_record(r) for r in rows]

    def count_records(self, pet_id: str) -> int:
        return len(self._rows("records", pet_id=pet_id))

    def set_review_status(self, record_id: str, status: ReviewStatus) -> None:
        self._b._transact(
            [
                self._update_op(f"REC#{record_id}", {"review_status": status.value}),
                self._audit_op(f"record_{status.value}", record_id),
            ]
        )
        log_event("human_review", record_id=record_id, decision=status.value)

    # -- reminders -----------------------------------------------------------------------------
    def save_reminder(self, reminder: Reminder) -> str:
        reminder.reminder_id = reminder.reminder_id or _new_id("rem")
        row = {**reminder_to_row(reminder), "created_at": utc_now_iso()}
        self._b._transact(
            [self._put_op("reminders", row), self._audit_op("reminder_created", reminder.reminder_id, reminder.label)]
        )
        log_event(
            "reminder_created",
            reminder_id=reminder.reminder_id,
            record_id=reminder.record_id,
            due_date=reminder.due_date.isoformat(),
        )
        return reminder.reminder_id

    def list_reminders(self, pet_id: str) -> list[Reminder]:
        rows = sorted(self._rows("reminders", pet_id=pet_id), key=lambda r: (r["due_date"], r["created_at"]))
        return [row_to_reminder(r) for r in rows]

    # -- conflicts -----------------------------------------------------------------------------
    def save_conflict_if_absent(self, conflict: Conflict) -> Optional[str]:
        conflict_id = conflict_id_for(conflict)
        row = {**conflict_to_row(conflict, conflict_id), "created_at": utc_now_iso()}
        written = self._b._transact(
            [
                self._put_op("conflicts", row, condition="attribute_not_exists(SK)"),
                self._audit_op("contradiction_detected", conflict_id, conflict.field),
            ]
        )
        if not written:
            return None
        log_event("contradiction_detected", conflict_id=conflict_id, field=conflict.field)
        return conflict_id

    def get_conflict(self, conflict_id: str) -> Optional[Row]:
        return self._row(f"CFT#{conflict_id}")

    def list_conflicts(self, pet_id: str, unresolved_only: bool = False) -> list[Row]:
        filters: dict[str, Any] = {"pet_id": pet_id}
        if unresolved_only:
            filters["resolved"] = 0
        return sorted(self._rows("conflicts", **filters), key=lambda r: (r["created_at"], r["conflict_id"]))

    def resolve_conflict(self, conflict_id: str) -> None:
        self._b._transact(
            [
                self._update_op(f"CFT#{conflict_id}", {"resolved": 1}),
                self._audit_op("conflict_resolved", conflict_id),
            ]
        )

    # -- audit ---------------------------------------------------------------------------------
    def audit_trail(self, limit: int = 100) -> list[Row]:
        items = self._b._query(self._pk, "AUDIT#", descending=True, limit=limit)
        return [{k: item.get(k) for k in ("id", "event", "ref_id", "detail", "created_at")} for item in items]
