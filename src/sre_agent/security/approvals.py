from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ApprovalRecord:
    id: str
    action: str
    payload: str
    reason: str
    requested_by: str
    state: str


class ApprovalStore(Protocol):
    def create(self, action: str, payload: str, reason: str, requested_by: str) -> ApprovalRecord: ...
    def decide(self, approval_id: str, approved: bool) -> ApprovalRecord: ...
    def get(self, approval_id: str) -> ApprovalRecord | None: ...


class MemoryApprovalStore:
    def __init__(self) -> None:
        self._rows: dict[str, ApprovalRecord] = {}

    def create(self, action: str, payload: str, reason: str, requested_by: str) -> ApprovalRecord:
        rec = ApprovalRecord(uuid.uuid4().hex[:12], action, payload, reason, requested_by, "pending")
        self._rows[rec.id] = rec
        return rec

    def decide(self, approval_id: str, approved: bool) -> ApprovalRecord:
        rec = self._rows[approval_id]
        rec.state = "approved_not_executed" if approved else "rejected"
        return rec

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._rows.get(approval_id)


class PostgresApprovalStore:
    def __init__(self, database_url: str) -> None:
        from sre_agent.db import connect, init_schema

        self._conn = connect(database_url)
        init_schema(self._conn)

    def create(self, action: str, payload: str, reason: str, requested_by: str) -> ApprovalRecord:
        rec = ApprovalRecord(uuid.uuid4().hex[:12], action, payload, reason, requested_by, "pending")
        self._conn.execute(
            "INSERT INTO approvals (id, action, payload, reason, requested_by, state) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (rec.id, rec.action, rec.payload, rec.reason, rec.requested_by, rec.state),
        )
        return rec

    def decide(self, approval_id: str, approved: bool) -> ApprovalRecord:
        state = "approved_not_executed" if approved else "rejected"
        self._conn.execute("UPDATE approvals SET state=%s WHERE id=%s", (state, approval_id))
        rec = self.get(approval_id)
        if rec is None:
            raise KeyError(approval_id)
        return rec

    def get(self, approval_id: str) -> ApprovalRecord | None:
        row = self._conn.execute("SELECT * FROM approvals WHERE id=%s", (approval_id,)).fetchone()
        if row is None:
            return None
        return ApprovalRecord(
            row["id"], row["action"], row["payload"], row["reason"], row["requested_by"], row["state"]
        )


def build_approval_store(database_url: str | None):
    if not database_url:
        return MemoryApprovalStore()
    return PostgresApprovalStore(database_url)
