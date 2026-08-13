"""Exercise persistence and atomic decisions against local durable backends."""

import os
import time
from collections.abc import Callable

from enterprise_genai_platform.state import (
    ApprovalStore,
    PostgreSQLApprovalStore,
    RedisApprovalStore,
)


def wait_until_connectable(factory: Callable[[], ApprovalStore], attempts: int = 10) -> None:
    """Wait for an authenticated host-side connection, not only container health."""
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            store = factory()
            store.close()
            return
        except Exception as error:  # noqa: BLE001 - readiness retries transport failures
            last_error = error
            time.sleep(1)
    raise RuntimeError("durable backend did not become connectable") from last_error


def verify(factory: Callable[[], ApprovalStore]) -> None:
    tenant = "payment-disputes"
    store = factory()
    pending = store.create_pending(
        request_id="durable-integration-request",
        requester="local-integration",
        query="sensitive synthetic request that must not be retained",
        tenant=tenant,
    )
    approval_id = pending.approval_id
    if len(pending.query_sha256) != 64:
        raise RuntimeError("backend did not persist a SHA-256 query digest")
    store.close()

    reopened = factory()
    persisted = reopened.get(approval_id, tenant=tenant)
    if persisted is None or persisted.status != "pending":
        raise RuntimeError("pending approval did not survive reconnect")
    approved = reopened.decide(
        approval_id,
        decision="approved",
        reviewer="local-reviewer",
        reason="local integration evidence checked",
        tenant=tenant,
    )
    if approved.status != "approved":
        raise RuntimeError("approval decision was not persisted")
    try:
        reopened.decide(
            approval_id,
            decision="rejected",
            reviewer="second-reviewer",
            reason="must be rejected atomically",
            tenant=tenant,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("backend allowed a second approval decision")
    reopened.close()


def main() -> None:
    postgres_url = os.environ["POSTGRES_STATE_URL"]
    redis_url = os.environ["REDIS_STATE_URL"]

    def postgres_factory() -> PostgreSQLApprovalStore:
        return PostgreSQLApprovalStore(postgres_url)

    def redis_factory() -> RedisApprovalStore:
        return RedisApprovalStore(redis_url)

    wait_until_connectable(postgres_factory)
    wait_until_connectable(redis_factory)
    verify(postgres_factory)
    verify(redis_factory)
    print("PostgreSQL and Redis durable-state integration passed")


if __name__ == "__main__":
    main()
