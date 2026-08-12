"""Parameterized SQLite approval store for pause-and-resume demonstrations."""

import hashlib
import sqlite3
from datetime import UTC, datetime
from threading import Lock
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from enterprise_genai_platform.metrics import PENDING_APPROVALS


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str
    request_id: str
    requester: str
    query_sha256: str
    status: Literal["pending", "approved", "rejected"]
    reviewer: str | None
    reason: str | None
    created_at: datetime
    decided_at: datetime | None


class ApprovalStore(Protocol):
    """Backend-neutral approval persistence contract."""

    def create_pending(self, *, request_id: str, requester: str, query: str) -> ApprovalRecord: ...

    def decide(
        self,
        approval_id: str,
        *,
        decision: Literal["approved", "rejected"],
        reviewer: str,
        reason: str,
    ) -> ApprovalRecord: ...

    def get(self, approval_id: str) -> ApprovalRecord | None: ...

    def close(self) -> None: ...


def build_pending_record(*, request_id: str, requester: str, query: str) -> ApprovalRecord:
    """Create a record without retaining the potentially sensitive query text."""
    return ApprovalRecord(
        approval_id=str(uuid4()),
        request_id=request_id,
        requester=requester,
        query_sha256=hashlib.sha256(query.encode()).hexdigest(),
        status="pending",
        reviewer=None,
        reason=None,
        created_at=datetime.now(UTC),
        decided_at=None,
    )


class SQLiteApprovalStore:
    def __init__(self, database_path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = Lock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    requester TEXT NOT NULL,
                    query_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
                    reviewer TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                )
                """
            )

    def create_pending(self, *, request_id: str, requester: str, query: str) -> ApprovalRecord:
        pending = build_pending_record(request_id=request_id, requester=requester, query=query)
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO approvals
                (approval_id, request_id, requester, query_sha256, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)""",
                (
                    pending.approval_id,
                    pending.request_id,
                    pending.requester,
                    pending.query_sha256,
                    pending.created_at.isoformat(),
                ),
            )
        record = self.get(pending.approval_id)
        if record is None:
            raise RuntimeError("Approval record was not persisted")
        PENDING_APPROVALS.inc()
        return record

    def decide(
        self,
        approval_id: str,
        *,
        decision: Literal["approved", "rejected"],
        reviewer: str,
        reason: str,
    ) -> ApprovalRecord:
        decided_at = datetime.now(UTC)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE approvals SET status = ?, reviewer = ?, reason = ?, decided_at = ?
                WHERE approval_id = ? AND status = 'pending'""",
                (decision, reviewer, reason, decided_at.isoformat(), approval_id),
            )
        if cursor.rowcount != 1:
            raise ValueError("Approval is missing or has already been decided")
        record = self.get(approval_id)
        if record is None:
            raise RuntimeError("Approval decision was not persisted")
        PENDING_APPROVALS.dec()
        return record

    def get(self, approval_id: str) -> ApprovalRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
        return ApprovalRecord.model_validate(dict(row)) if row else None

    def close(self) -> None:
        self._connection.close()

    def __del__(self) -> None:
        try:
            self._connection.close()
        except sqlite3.Error:
            pass
