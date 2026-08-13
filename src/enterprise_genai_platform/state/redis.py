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
if record.tenant ~= ARGV[5] then return nil end
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

    def _tenant_pending_key(self, tenant: str) -> str:
        # A per-tenant index set, never a scan across all approvals: listing
        # tenant A's pending approvals must not require reading (and
        # therefore transiently holding in memory) tenant B's records at all.
        return f"{self._key_prefix}pending-index:{tenant}"

    def create_pending(
        self, *, request_id: str, requester: str, query: str, tenant: str
    ) -> ApprovalRecord:
        pending = build_pending_record(
            request_id=request_id, requester=requester, query=query, tenant=tenant
        )
        created = self._client.set(
            self._key(pending.approval_id), pending.model_dump_json(), nx=True
        )
        if not created:
            raise RuntimeError("Approval record was not persisted")
        self._client.sadd(self._tenant_pending_key(tenant), pending.approval_id)
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
        from datetime import UTC, datetime

        result = self._client.eval(
            DECIDE_SCRIPT,
            1,
            self._key(approval_id),
            decision,
            reviewer,
            reason,
            datetime.now(UTC).isoformat(),
            tenant,
        )
        if result is None:
            raise ValueError("Approval is missing, already decided, or belongs to another tenant")
        record = ApprovalRecord.model_validate(json.loads(cast(str, result)))
        self._client.srem(self._tenant_pending_key(record.tenant), approval_id)
        PENDING_APPROVALS.labels(record.tenant).dec()
        return record

    def get(self, approval_id: str, *, tenant: str) -> ApprovalRecord | None:
        value = self._client.get(self._key(approval_id))
        if not value:
            return None
        record = ApprovalRecord.model_validate_json(cast(str, value))
        return record if record.tenant == tenant else None

    def list_pending(self, *, tenant: str) -> tuple[ApprovalRecord, ...]:
        approval_ids = cast(set[str], self._client.smembers(self._tenant_pending_key(tenant)))
        records = (self.get(approval_id, tenant=tenant) for approval_id in approval_ids)
        return tuple(
            sorted(
                (record for record in records if record is not None and record.status == "pending"),
                key=lambda record: record.created_at,
            )
        )

    def close(self) -> None:
        self._client.close()
