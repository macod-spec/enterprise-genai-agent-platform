"""Cost-control primitives shared by operational entrypoints and tests."""

from __future__ import annotations

from datetime import UTC, datetime


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and normalise it to UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)
