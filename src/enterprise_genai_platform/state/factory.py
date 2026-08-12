"""Approval-store construction from validated runtime configuration."""

from typing import Literal

from enterprise_genai_platform.state.postgres import PostgreSQLApprovalStore
from enterprise_genai_platform.state.redis import RedisApprovalStore
from enterprise_genai_platform.state.store import ApprovalStore, SQLiteApprovalStore


def build_approval_store(
    backend: Literal["sqlite", "postgresql", "redis"],
    *,
    sqlite_path: str,
    connection_url: str | None,
) -> ApprovalStore:
    if backend == "sqlite":
        return SQLiteApprovalStore(sqlite_path)
    if not connection_url:
        raise ValueError(f"STATE_CONNECTION_URL is required for the {backend} backend")
    if backend == "postgresql":
        return PostgreSQLApprovalStore(connection_url)
    return RedisApprovalStore(connection_url)
