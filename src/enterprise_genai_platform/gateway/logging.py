"""Structured, redaction-aware application logging."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

_REDACTED_KEYS = {"authorization", "cookie", "password", "secret", "token"}


def redact(value: Any) -> Any:
    """Recursively redact values whose keys indicate sensitive data."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _REDACTED_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Emit machine-readable logs without serializing request bodies or credentials."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "event_fields", None)
        if isinstance(fields, dict):
            payload.update(redact(fields))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str) -> None:
    """Configure the root logger for local and container execution."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
