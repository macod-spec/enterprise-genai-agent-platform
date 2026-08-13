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
    tenant: str
    query_sha256: str
    status: Literal["pending", "approved", "rejected"]
    reviewer: str | None
    reason: str | None
    created_at: datetime
    decided_at: datetime | None


class ApprovalStore(Protocol):
    """Backend-neutral approval persistence contract.

    Every method that touches a record takes the caller's tenant explicitly
    — including single-record lookups by ID — so no code path can read or
    modify state without declaring which tenant it is acting as. The
    Postgres backend enforces this at the database layer via Row-Level
    Security; SQLite and Redis enforce it in the query/lookup itself. Either
    way, a record belonging to a different tenant than the one requested
    must never be returned.
    """

    def create_pending(
        self, *, request_id: str, requester: str, query: str, tenant: str
    ) -> ApprovalRecord: ...

    def decide(
        self,
        approval_id: str,
        *,
        decision: Literal["approved", "rejected"],
        reviewer: str,
        reason: str,
        tenant: str,
    ) -> ApprovalRecord: ...

    def get(self, approval_id: str, *, tenant: str) -> ApprovalRecord | None: ...

    def list_pending(self, *, tenant: str) -> tuple[ApprovalRecord, ...]: ...

    def close(self) -> None: ...


def build_pending_record(
    *, request_id: str, requester: str, query: str, tenant: str
) -> ApprovalRecord:
    """Create a record without retaining the potentially sensitive query text."""
    return ApprovalRecord(
        approval_id=str(uuid4()),
        request_id=request_id,
        requester=requester,
        tenant=tenant,
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
                    tenant TEXT NOT NULL,
                    query_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
                    reviewer TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_approvals_tenant_status "
                "ON approvals (tenant, status)"
            )

    def create_pending(
        self, *, request_id: str, requester: str, query: str, tenant: str
    ) -> ApprovalRecord:
        pending = build_pending_record(
            request_id=request_id, requester=requester, query=query, tenant=tenant
        )
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO approvals
                (approval_id, request_id, requester, tenant, query_sha256, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    pending.approval_id,
                    pending.request_id,
                    pending.requester,
                    pending.tenant,
                    pending.query_sha256,
                    pending.created_at.isoformat(),
                ),
            )
        record = self.get(pending.approval_id, tenant=tenant)
        if record is None:
            raise RuntimeError("Approval record was not persisted")
        PENDING_APPROVALS.labels(record.tenant).inc()
        return record

    def decide(
        self,
        approval_id: str,
        *,
        decision: Literal["approved", "rejected"],
        reviewer: str,
        reason: str,
        tenant: str,
    ) -> ApprovalRecord:
        decided_at = datetime.now(UTC)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE approvals SET status = ?, reviewer = ?, reason = ?, decided_at = ?
                WHERE approval_id = ? AND status = 'pending' AND tenant = ?""",
                (decision, reviewer, reason, decided_at.isoformat(), approval_id, tenant),
            )
        if cursor.rowcount != 1:
            raise ValueError("Approval is missing, already decided, or belongs to another tenant")
        record = self.get(approval_id, tenant=tenant)
        if record is None:
            raise RuntimeError("Approval decision was not persisted")
        PENDING_APPROVALS.labels(record.tenant).dec()
        return record

    def get(self, approval_id: str, *, tenant: str) -> ApprovalRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ? AND tenant = ?",
                (approval_id, tenant),
            ).fetchone()
        return ApprovalRecord.model_validate(dict(row)) if row else None

    def list_pending(self, *, tenant: str) -> tuple[ApprovalRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM approvals WHERE tenant = ? AND status = 'pending' "
                "ORDER BY created_at",
                (tenant,),
            ).fetchall()
        return tuple(ApprovalRecord.model_validate(dict(row)) for row in rows)

    def close(self) -> None:
        self._connection.close()

    def __del__(self) -> None:
        try:
            self._connection.close()
        except sqlite3.Error:
            pass
