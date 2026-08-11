"""Exercise persistence and atomic decisions against local durable backends."""

import os
from collections.abc import Callable

from enterprise_genai_platform.state import (
    ApprovalStore,
    PostgreSQLApprovalStore,
    RedisApprovalStore,
)


def verify(factory: Callable[[], ApprovalStore]) -> None:
    store = factory()
    pending = store.create_pending(
        request_id="durable-integration-request",
        requester="local-integration",
        query="sensitive synthetic request that must not be retained",
    )
    approval_id = pending.approval_id
    if len(pending.query_sha256) != 64:
        raise RuntimeError("backend did not persist a SHA-256 query digest")
    store.close()

    reopened = factory()
    persisted = reopened.get(approval_id)
    if persisted is None or persisted.status != "pending":
        raise RuntimeError("pending approval did not survive reconnect")
    approved = reopened.decide(
        approval_id,
        decision="approved",
        reviewer="local-reviewer",
        reason="local integration evidence checked",
    )
    if approved.status != "approved":
        raise RuntimeError("approval decision was not persisted")
    try:
        reopened.decide(
            approval_id,
            decision="rejected",
            reviewer="second-reviewer",
            reason="must be rejected atomically",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("backend allowed a second approval decision")
    reopened.close()


def main() -> None:
    postgres_url = os.environ["POSTGRES_STATE_URL"]
    redis_url = os.environ["REDIS_STATE_URL"]
    verify(lambda: PostgreSQLApprovalStore(postgres_url))
    verify(lambda: RedisApprovalStore(redis_url))
    print("PostgreSQL and Redis durable-state integration passed")


if __name__ == "__main__":
    main()
