"""Live verification that Postgres RLS survives connection-pool reuse.

Excluded from the default test run (`pytest -m "not live_postgres"`, the
default addopts) because it needs a real Postgres server; unit tests mock
the pg8000 driver and so cannot exercise Postgres's own RLS engine or its
`set_config(..., is_local => true)` transaction-scoping behaviour, which is
exactly what `PostgreSQLApprovalStore` (state/postgres.py) depends on for
isolation. Run explicitly with `make live-verification-postgres`.

The property under test: with a connection pool of size 1 — forcing every
request to share the *same* physical connection — a request for tenant B
immediately followed by a request for tenant A on that same connection must
never see tenant B's data. If `set_config` were session-scoped (a bare `SET`)
rather than transaction-scoped (`is_local => true`), or if the table lacked
`FORCE ROW LEVEL SECURITY`, this test would catch it; the unit test suite,
which never touches a pooled physical connection twice, cannot.
"""

import socket
import subprocess
import time
import uuid
from collections.abc import Iterator

import pytest

from enterprise_genai_platform.state.postgres import PostgreSQLApprovalStore

pytestmark = pytest.mark.live_postgres

_TENANT_A = "payment-disputes"
_TENANT_B = "complaints-triage"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def _wait_until_ready(container_name: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container_name, "pg_isready", "-U", "postgres"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"Postgres container {container_name!r} never became ready")


def _create_unprivileged_app_role(container_name: str) -> None:
    """Create the role the store actually connects as.

    This is the detail that makes the test meaningful: Postgres superusers
    (and any role with BYPASSRLS) ignore Row-Level Security unconditionally
    — `FORCE ROW LEVEL SECURITY` has no effect on them at all, it only
    corrects the *owner*-bypass default for an ordinary role. Connecting as
    the `postgres` superuser, as the container's default admin connection
    does, would make this test pass even if RLS enforcement were completely
    broken. `novabank_app` is deliberately a plain LOGIN role with no
    superuser or BYPASSRLS attribute, matching how a real deployment must be
    configured; it still becomes the approvals table's owner (it is the role
    that CREATEs it), which is exactly the case FORCE is needed for.
    """
    subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "psql",
            "-U",
            "postgres",
            # Schema privileges are per-database: granting against the
            # default `postgres` database (the -d omitted) would silently
            # leave `novabank_rls_test`'s own public schema untouched.
            "-d",
            "novabank_rls_test",
            "-c",
            "CREATE ROLE novabank_app LOGIN PASSWORD 'novabank_app' "  # pragma: allowlist secret
            "NOSUPERUSER NOBYPASSRLS; "
            "GRANT ALL ON SCHEMA public TO novabank_app;",
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="module")
def connection_url() -> Iterator[str]:
    """Start a throwaway Postgres container for this test module only.

    Docker, not docker-compose, deliberately: this is the only test that
    needs a database, so a persistent compose stack would be a standing cost
    (and drift risk) for one module's coverage.
    """
    container_name = f"novabank-rls-pool-test-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            "-e",
            "POSTGRES_PASSWORD=postgres",  # pragma: allowlist secret
            "-e",
            "POSTGRES_DB=novabank_rls_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:16-alpine",
        ],
        check=True,
        capture_output=True,
    )
    try:
        _wait_until_ready(container_name)
        # pg8000 connects immediately after pg_isready reports ready in CI
        # environments too, but a short grace period avoids flakiness from
        # the server finishing its post-ready initialization.
        time.sleep(0.5)
        _create_unprivileged_app_role(container_name)
        # pragma: allowlist secret -- ephemeral, localhost-only, throwaway container
        yield f"postgres://novabank_app:novabank_app@127.0.0.1:{port}/novabank_rls_test"
    finally:
        subprocess.run(["docker", "stop", container_name], check=False, capture_output=True)


def test_pooled_connection_reuse_never_leaks_a_tenant_across_requests(
    connection_url: str,
) -> None:
    # size=1 is the point: every request below is forced onto the same
    # physical connection, the exact scenario that would expose a session-
    # scoped (rather than transaction-scoped) tenant setting.
    store = PostgreSQLApprovalStore(connection_url, pool_size=1)
    try:
        pending_b = store.create_pending(
            request_id="req-b-1", requester="b-user", query="tenant B query", tenant=_TENANT_B
        )
        pending_a = store.create_pending(
            request_id="req-a-1", requester="a-user", query="tenant A query", tenant=_TENANT_A
        )

        # Interleave on the single shared connection: B, then A, then B
        # again, immediately re-reading each record on the *other* tenant's
        # request to prove the previous transaction's tenant setting left no
        # trace behind for the next one to inherit.
        assert store.get(pending_b.approval_id, tenant=_TENANT_B) is not None
        assert store.get(pending_b.approval_id, tenant=_TENANT_A) is None
        assert store.get(pending_a.approval_id, tenant=_TENANT_A) is not None
        assert store.get(pending_a.approval_id, tenant=_TENANT_B) is None
        assert store.get(pending_b.approval_id, tenant=_TENANT_B) is not None

        a_pending = store.list_pending(tenant=_TENANT_A)
        b_pending = store.list_pending(tenant=_TENANT_B)
        assert {record.approval_id for record in a_pending} == {pending_a.approval_id}
        assert {record.approval_id for record in b_pending} == {pending_b.approval_id}
    finally:
        store.close()


def test_pooled_connection_reuse_never_leaks_across_decide_calls(connection_url: str) -> None:
    store = PostgreSQLApprovalStore(connection_url, pool_size=1)
    try:
        pending_b = store.create_pending(
            request_id="req-b-2", requester="b-user", query="tenant B query", tenant=_TENANT_B
        )
        pending_a = store.create_pending(
            request_id="req-a-2", requester="a-user", query="tenant A query", tenant=_TENANT_A
        )

        with pytest.raises(
            ValueError, match="missing, already decided, or belongs to another tenant"
        ):
            store.decide(
                pending_b.approval_id,
                decision="approved",
                reviewer="a-reviewer",
                reason="wrong tenant",
                tenant=_TENANT_A,
            )

        decided = store.decide(
            pending_a.approval_id,
            decision="approved",
            reviewer="a-reviewer",
            reason="correct tenant",
            tenant=_TENANT_A,
        )
        assert decided.status == "approved"
        # The rejected cross-tenant decide() above must not have mutated B's
        # record despite sharing the same pooled connection as A's decide().
        untouched = store.get(pending_b.approval_id, tenant=_TENANT_B)
        assert untouched is not None
        assert untouched.status == "pending"
    finally:
        store.close()
