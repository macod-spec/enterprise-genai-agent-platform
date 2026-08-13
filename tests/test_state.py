"""Persistent human-approval state tests."""

import pytest
from pydantic import ValidationError

from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.state import SQLiteApprovalStore
from enterprise_genai_platform.state.factory import build_approval_store


def test_approval_lifecycle_stores_only_query_hash() -> None:
    store = SQLiteApprovalStore()
    pending = store.create_pending(
        request_id="request-1",
        requester="operator",
        query="Refund synthetic transaction",
        tenant="payment-disputes",
    )

    assert pending.status == "pending"
    assert len(pending.query_sha256) == 64
    assert "Refund" not in pending.query_sha256

    approved = store.decide(
        pending.approval_id,
        decision="approved",
        reviewer="reviewer",
        reason="Evidence checked",
        tenant="payment-disputes",
    )

    assert approved.status == "approved"
    assert approved.reviewer == "reviewer"
    assert approved.decided_at is not None

    with pytest.raises(ValueError, match="missing, already decided, or belongs to another tenant"):
        store.decide(
            pending.approval_id,
            decision="rejected",
            reviewer="other",
            reason="Duplicate decision",
            tenant="payment-disputes",
        )
    store.close()


def test_unknown_approval_returns_none() -> None:
    store = SQLiteApprovalStore()
    assert store.get("missing", tenant="payment-disputes") is None
    store.close()


def test_approval_from_another_tenant_is_not_visible() -> None:
    store = SQLiteApprovalStore()
    pending = store.create_pending(
        request_id="request-1",
        requester="operator",
        query="Refund synthetic transaction",
        tenant="payment-disputes",
    )
    assert store.get(pending.approval_id, tenant="complaints-triage") is None
    with pytest.raises(ValueError, match="missing, already decided, or belongs to another tenant"):
        store.decide(
            pending.approval_id,
            decision="approved",
            reviewer="reviewer",
            reason="Evidence checked",
            tenant="complaints-triage",
        )
    store.close()


def test_remote_backend_requires_connection_url() -> None:
    with pytest.raises(ValidationError, match="STATE_CONNECTION_URL"):
        Settings(state_backend="postgresql")


def test_production_rejects_sqlite_state() -> None:
    with pytest.raises(ValidationError, match="SQLite state"):
        Settings(app_env="production")


def test_factory_builds_sqlite_and_rejects_missing_remote_url() -> None:
    store = build_approval_store("sqlite", sqlite_path=":memory:", connection_url=None)
    assert isinstance(store, SQLiteApprovalStore)
    store.close()
    with pytest.raises(ValueError, match="STATE_CONNECTION_URL"):
        build_approval_store("redis", sqlite_path=":memory:", connection_url=None)
