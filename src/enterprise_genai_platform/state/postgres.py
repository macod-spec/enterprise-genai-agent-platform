"""PostgreSQL approval persistence with parameterized, atomic updates."""

from threading import Lock
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from pg8000 import dbapi  # type: ignore[import-untyped]

from enterprise_genai_platform.metrics import PENDING_APPROVALS
from enterprise_genai_platform.state.store import ApprovalRecord, build_pending_record

RECORD_COLUMNS = (
    "approval_id",
    "request_id",
    "requester",
    "query_sha256",
    "status",
    "reviewer",
    "reason",
    "created_at",
    "decided_at",
)


def _record(row: tuple[Any, ...]) -> ApprovalRecord:
    values = dict(zip(RECORD_COLUMNS, row, strict=True))
    values["approval_id"] = str(values["approval_id"])
    return ApprovalRecord.model_validate(values)


class PostgreSQLApprovalStore:
    def __init__(self, connection_url: str) -> None:
        parsed = urlparse(connection_url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise ValueError("STATE_CONNECTION_URL must be a valid PostgreSQL URL")
        self._connection = dbapi.connect(
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/"),
            timeout=5,
        )
        self._lock = Lock()
        cursor = self._connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id UUID PRIMARY KEY,
                request_id TEXT NOT NULL,
                requester TEXT NOT NULL,
                query_sha256 CHAR(64) NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
                reviewer TEXT,
                reason TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                decided_at TIMESTAMPTZ
            )
            """
        )
        self._connection.commit()

    def create_pending(self, *, request_id: str, requester: str, query: str) -> ApprovalRecord:
        pending = build_pending_record(request_id=request_id, requester=requester, query=query)
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(
                """INSERT INTO approvals
                (approval_id, request_id, requester, query_sha256, status, created_at)
                VALUES (%s, %s, %s, %s, 'pending', %s)""",
                (
                    pending.approval_id,
                    pending.request_id,
                    pending.requester,
                    pending.query_sha256,
                    pending.created_at,
                ),
            )
            self._connection.commit()
        PENDING_APPROVALS.inc()
        return pending

    def decide(
        self,
        approval_id: str,
        *,
        decision: Literal["approved", "rejected"],
        reviewer: str,
        reason: str,
    ) -> ApprovalRecord:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(
                """UPDATE approvals
                SET status = %s, reviewer = %s, reason = %s, decided_at = CURRENT_TIMESTAMP
                WHERE approval_id = %s AND status = 'pending'
                RETURNING approval_id, request_id, requester, query_sha256, status,
                          reviewer, reason, created_at, decided_at""",
                (decision, reviewer, reason, approval_id),
            )
            row = cursor.fetchone()
            self._connection.commit()
        if row is None:
            raise ValueError("Approval is missing or has already been decided")
        PENDING_APPROVALS.dec()
        return _record(row)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(
                """SELECT approval_id, request_id, requester, query_sha256, status,
                          reviewer, reason, created_at, decided_at
                   FROM approvals WHERE approval_id = %s""",
                (approval_id,),
            )
            row = cursor.fetchone()
        return _record(row) if row else None

    def close(self) -> None:
        self._connection.close()
