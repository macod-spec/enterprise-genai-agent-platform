"""Authentication and authorization boundaries for gateway routes."""

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from enterprise_genai_platform.gateway.config import Settings


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated caller identity supplied to agent platform services."""

    subject: str
    roles: frozenset[str]


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_principal(
    request: Request,
    user: str | None = Header(default=None, alias="X-Local-User"),
    roles: str = Header(default="", alias="X-Local-Roles"),
) -> Principal:
    """Authenticate a local caller; production identity will use verified Entra tokens."""
    settings = _settings(request)
    if settings.app_env not in {"local", "test"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production identity provider is not configured",
        )
    if user is None or not user.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Local identity header is required",
            headers={"WWW-Authenticate": "Local"},
        )
    normalized_roles = frozenset(role.strip() for role in roles.split(",") if role.strip())
    return Principal(subject=user.strip(), roles=normalized_roles)


AuthenticatedPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(*required_roles: str) -> Callable[[AuthenticatedPrincipal], Principal]:
    """Create a dependency requiring every named platform role."""

    def authorize(principal: AuthenticatedPrincipal) -> Principal:
        missing = set(required_roles) - principal.roles
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Caller does not have the required role",
            )
        return principal

    return authorize


class InMemoryRateLimiter:
    """Process-local sliding-window limiter for development and test execution."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """Raise HTTP 429 when a caller has exhausted its configured allowance."""
        now = time.monotonic()
        requests = self._requests[key]
        while requests and requests[0] <= now - self._window:
            requests.popleft()
        if len(requests) >= self._limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(self._window)},
            )
        requests.append(now)


def enforce_rate_limit(
    request: Request,
    principal: AuthenticatedPrincipal,
) -> Principal:
    """Apply the development limiter after the caller has been authenticated."""
    limiter: InMemoryRateLimiter = request.app.state.rate_limiter
    limiter.check(principal.subject)
    return principal
