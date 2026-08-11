"""Redis approval persistence using atomic compare-and-set decisions."""

import json
from typing import Literal, cast

from redis import Redis

from enterprise_genai_platform.metrics import PENDING_APPROVALS
from enterprise_genai_platform.state.store import ApprovalRecord, build_pending_record

DECIDE_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then return nil end
local record = cjson.decode(current)
if record.status ~= 'pending' then return nil end
record.status = ARGV[1]
record.reviewer = ARGV[2]
record.reason = ARGV[3]
record.decided_at = ARGV[4]
local updated = cjson.encode(record)
redis.call('SET', KEYS[1], updated)
return updated
"""


class RedisApprovalStore:
    def __init__(
        self, connection_url: str, *, key_prefix: str = "agent-platform:approval:"
    ) -> None:
        self._client: Redis = Redis.from_url(
            connection_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5
        )
        self._client.ping()
        self._key_prefix = key_prefix

    def _key(self, approval_id: str) -> str:
        return f"{self._key_prefix}{approval_id}"

    def create_pending(self, *, request_id: str, requester: str, query: str) -> ApprovalRecord:
        pending = build_pending_record(request_id=request_id, requester=requester, query=query)
        created = self._client.set(
            self._key(pending.approval_id), pending.model_dump_json(), nx=True
        )
        if not created:
            raise RuntimeError("Approval record was not persisted")
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
        from datetime import UTC, datetime

        result = self._client.eval(
            DECIDE_SCRIPT,
            1,
            self._key(approval_id),
            decision,
            reviewer,
            reason,
            datetime.now(UTC).isoformat(),
        )
        if result is None:
            raise ValueError("Approval is missing or has already been decided")
        PENDING_APPROVALS.dec()
        return ApprovalRecord.model_validate(json.loads(cast(str, result)))

    def get(self, approval_id: str) -> ApprovalRecord | None:
        value = self._client.get(self._key(approval_id))
        return ApprovalRecord.model_validate_json(cast(str, value)) if value else None

    def close(self) -> None:
        self._client.close()
