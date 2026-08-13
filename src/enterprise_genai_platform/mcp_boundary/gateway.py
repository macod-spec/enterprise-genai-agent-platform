"""Deny-by-default MCP tool gateway with security and reliability controls."""

import asyncio
import hashlib
import json
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from pydantic import BaseModel, ValidationError

from enterprise_genai_platform.mcp_boundary.contracts import AuditRecord, CallerContext
from enterprise_genai_platform.metrics import MCP_CALLS, MCP_DURATION


class MCPGatewayError(RuntimeError):
    """Base exception safe for mapping to a controlled agent result."""


class MCPAccessDenied(MCPGatewayError):
    pass


class MCPToolNotFound(MCPGatewayError):
    pass


class MCPInvalidArguments(MCPGatewayError):
    pass


class MCPToolFailure(MCPGatewayError):
    pass


@dataclass(frozen=True, slots=True)
class ToolRegistration[InputT: BaseModel, OutputT: BaseModel]:
    name: str
    allowed_agents: frozenset[str]
    required_roles: frozenset[str]
    input_model: type[InputT]
    output_model: type[OutputT]
    handler: Callable[[InputT, CallerContext], Awaitable[OutputT]]


class AuditSink:
    """Append-only in-memory sink; external durable export is added with observability."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self._records.append(record)

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)


class GovernedMCPGateway:
    """Execute only registered tools under explicit caller and agent policy."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 2.0,
        max_attempts: int = 2,
        rate_limit: int = 30,
        rate_window_seconds: int = 60,
        audit_sink: AuditSink | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_attempts < 1 or rate_limit < 1:
            raise ValueError("MCP limits must be positive")
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._rate_limit = rate_limit
        self._rate_window = rate_window_seconds
        self._tools: dict[str, ToolRegistration[Any, Any]] = {}
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self.audit = audit_sink or AuditSink()

    def register(self, registration: ToolRegistration[Any, Any]) -> None:
        if registration.name in self._tools:
            raise ValueError(f"Duplicate MCP tool registration: {registration.name}")
        self._tools[registration.name] = registration

    @property
    def approved_tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    async def invoke(
        self,
        tool_name: str,
        arguments: dict[str, object],
        caller: CallerContext,
    ) -> BaseModel:
        started = time.perf_counter()
        fingerprint = self._fingerprint(arguments)
        attempts = 0
        outcome: Literal["success", "denied", "invalid", "timeout", "error"] = "error"
        try:
            registration = self._tools.get(tool_name)
            if registration is None:
                outcome = "denied"
                raise MCPToolNotFound("Tool is not approved")
            if caller.agent not in registration.allowed_agents:
                outcome = "denied"
                raise MCPAccessDenied("Agent is not permitted to use this tool")
            if not registration.required_roles <= caller.roles:
                outcome = "denied"
                raise MCPAccessDenied("Caller lacks the required tool role")
            try:
                self._check_rate_limit(caller.subject, tool_name)
            except MCPAccessDenied:
                outcome = "denied"
                raise
            try:
                validated_input = registration.input_model.model_validate(arguments)
            except ValidationError as exc:
                outcome = "invalid"
                raise MCPInvalidArguments("Tool arguments failed schema validation") from exc

            for attempts in range(1, self._max_attempts + 1):
                try:
                    async with asyncio.timeout(self._timeout):
                        raw_output = await registration.handler(validated_input, caller)
                    output = registration.output_model.model_validate(raw_output)
                    outcome = "success"
                    return cast(BaseModel, output)
                except TimeoutError:
                    outcome = "timeout"
                except (LookupError, ValidationError) as exc:
                    outcome = "error"
                    raise MCPToolFailure("Tool returned no valid result") from exc
                except Exception as exc:
                    outcome = "error"
                    if attempts == self._max_attempts:
                        raise MCPToolFailure("Tool execution failed") from exc
            raise MCPToolFailure("Tool execution timed out")
        finally:
            duration_seconds = time.perf_counter() - started
            MCP_CALLS.labels(tool_name if tool_name in self._tools else "unapproved", outcome).inc()
            MCP_DURATION.labels(tool_name if tool_name in self._tools else "unapproved").observe(
                duration_seconds
            )
            self.audit.append(
                AuditRecord(
                    request_id=caller.request_id,
                    subject=caller.subject,
                    agent=caller.agent,
                    tool=tool_name,
                    argument_fingerprint=fingerprint,
                    outcome=outcome,
                    duration_ms=round(duration_seconds * 1000, 3),
                    attempt_count=attempts,
                )
            )

    def _check_rate_limit(self, subject: str, tool_name: str) -> None:
        now = time.monotonic()
        key = f"{subject}:{tool_name}"
        requests = self._requests[key]
        while requests and requests[0] <= now - self._rate_window:
            requests.popleft()
        if len(requests) >= self._rate_limit:
            raise MCPAccessDenied("Tool rate limit exceeded")
        requests.append(now)

    @staticmethod
    def _fingerprint(arguments: dict[str, object]) -> str:
        canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()
