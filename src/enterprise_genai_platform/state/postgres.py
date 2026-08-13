"""PostgreSQL approval persistence, tenant-isolated with Row-Level Security.

ADR-0XX (multi-tenancy) explains the choice of RLS over schema-per-tenant.
The property this module exists to guarantee: a connection returned to the
pool after tenant A's request and handed to tenant B's request next carries
no trace of A's tenant context. That is guaranteed by using
`set_config(..., is_local => true)` — the parameterized equivalent of
`SET LOCAL` — inside the same transaction as every query, never a bare
`SET` (session-scoped, and exactly the setting that would leak across
pooled reuse). Postgres resets a `SET LOCAL`/`is_local` value automatically
at COMMIT or ROLLBACK regardless of what happens to the underlying
connection afterwards, so leakage is structurally prevented rather than
merely tested for — the test in
tests/integration/test_postgres_rls_pool.py (run via
`make live-verification-postgres`, since it needs a real Postgres server)
exists to catch a regression, not to be the only thing standing between a
bug and a data breach.
"""

import queue
from contextlib import contextmanager
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
    "tenant",
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


def _connect(parsed_url: Any, *, timeout: int = 5) -> Any:
    return dbapi.connect(
        user=unquote(parsed_url.username or ""),
        password=unquote(parsed_url.password or ""),
        host=parsed_url.hostname,
        port=parsed_url.port or 5432,
        database=parsed_url.path.lstrip("/"),
        timeout=timeout,
    )


class PostgresConnectionPool:
    """A small, fixed-size, thread-safe pool of pg8000 connections.

    Deliberately not a new dependency: pg8000 has no first-party pool, and
    the platform otherwise has no pooled Postgres access, so a minimal
    wrapper is proportionate. `size` is intentionally kept small in tests —
    a pool of 1 is what actually forces the connection-reuse scenario RLS
    must survive; a pool sized comfortably larger than concurrent demand
    would never exercise it.
    """

    def __init__(self, connection_url: str, *, size: int) -> None:
        if size < 1:
            raise ValueError("Connection pool size must be at least 1")
        parsed = urlparse(connection_url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise ValueError("connection_url must be a valid PostgreSQL URL")
        self._connections: queue.Queue[Any] = queue.Queue(maxsize=size)
        for _ in range(size):
            self._connections.put(_connect(parsed))

    @contextmanager
    def connection(self) -> Any:
        conn = self._connections.get()
        try:
            yield conn
        finally:
            self._connections.put(conn)

    def close(self) -> None:
        while not self._connections.empty():
            self._connections.get().close()


class PostgreSQLApprovalStore:
    def __init__(self, connection_url: str, *, pool_size: int = 5) -> None:
        self._pool = PostgresConnectionPool(connection_url, size=pool_size)
        self._lock = Lock()
        with self._pool.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id UUID PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    requester TEXT NOT NULL,
                    tenant TEXT NOT NULL,
                    query_sha256 CHAR(64) NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
                    reviewer TEXT,
                    reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    decided_at TIMESTAMPTZ
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_approvals_tenant_status "
                "ON approvals (tenant, status)"
            )
            cursor.execute("ALTER TABLE approvals ENABLE ROW LEVEL SECURITY")
            # FORCE, not just ENABLE: RLS is bypassed for the table owner by
            # default, and the connecting role — having just CREATEd the
            # table — normally is the owner. Without FORCE this entire
            # module would silently provide no isolation at all.
            cursor.execute("ALTER TABLE approvals FORCE ROW LEVEL SECURITY")
            cursor.execute("DROP POLICY IF EXISTS tenant_isolation ON approvals")
            cursor.execute(
                """CREATE POLICY tenant_isolation ON approvals
                   USING (tenant = current_setting('app.tenant_id', true))
                   WITH CHECK (tenant = current_setting('app.tenant_id', true))"""
            )
            connection.commit()

    @contextmanager
    def _tenant_scoped_cursor(self, tenant: str) -> Any:
        """One transaction, scoped to one tenant via a parameterized
        set_config(..., is_local => true) — never a bare SET, which is
        session- not transaction-scoped and is exactly the persistence
        across pooled reuse this design must not have."""
        with self._lock, self._pool.connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
            try:
                yield cursor
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def create_pending(
        self, *, request_id: str, requester: str, query: str, tenant: str
    ) -> ApprovalRecord:
        pending = build_pending_record(
            request_id=request_id, requester=requester, query=query, tenant=tenant
        )
        with self._tenant_scoped_cursor(tenant) as cursor:
            cursor.execute(
                """INSERT INTO approvals
                (approval_id, request_id, requester, tenant, query_sha256, status, created_at)
                VALUES (%s, %s, %s, %s, %s, 'pending', %s)""",
                (
                    pending.approval_id,
                    pending.request_id,
                    pending.requester,
                    pending.tenant,
                    pending.query_sha256,
                    pending.created_at,
                ),
            )
        PENDING_APPROVALS.labels(tenant).inc()
        return pending

    def decide(
        self,
        approval_id: str,
        *,
        decision: Literal["approved", "rejected"],
        reviewer: str,
        reason: str,
        tenant: str,
    ) -> ApprovalRecord:
        with self._tenant_scoped_cursor(tenant) as cursor:
            cursor.execute(
                """UPDATE approvals
                SET status = %s, reviewer = %s, reason = %s, decided_at = CURRENT_TIMESTAMP
                WHERE approval_id = %s AND status = 'pending'
                RETURNING approval_id, request_id, requester, tenant, query_sha256, status,
                          reviewer, reason, created_at, decided_at""",
                (decision, reviewer, reason, approval_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError("Approval is missing, already decided, or belongs to another tenant")
        PENDING_APPROVALS.labels(tenant).dec()
        return _record(row)

    def get(self, approval_id: str, *, tenant: str) -> ApprovalRecord | None:
        with self._tenant_scoped_cursor(tenant) as cursor:
            cursor.execute(
                """SELECT approval_id, request_id, requester, tenant, query_sha256, status,
                          reviewer, reason, created_at, decided_at
                   FROM approvals WHERE approval_id = %s""",
                (approval_id,),
            )
            row = cursor.fetchone()
        return _record(row) if row else None

    def list_pending(self, *, tenant: str) -> tuple[ApprovalRecord, ...]:
        with self._tenant_scoped_cursor(tenant) as cursor:
            cursor.execute(
                """SELECT approval_id, request_id, requester, tenant, query_sha256, status,
                          reviewer, reason, created_at, decided_at
                   FROM approvals WHERE status = 'pending' ORDER BY created_at"""
            )
            rows = cursor.fetchall()
        return tuple(_record(row) for row in rows)

    def close(self) -> None:
        self._pool.close()
