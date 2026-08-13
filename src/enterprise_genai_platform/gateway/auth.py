"""Authentication and authorization boundaries for gateway routes."""

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.tenancy.context import TenantContext
from enterprise_genai_platform.tenancy.registry import TenantRegistry, UnknownTenantError


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


def get_tenant_context(
    request: Request,
    _principal: AuthenticatedPrincipal,
    tenant: str | None = Header(default=None, alias="X-Local-Tenant"),
) -> TenantContext:
    """Resolve tenant exactly once, at the gateway edge, from the caller's
    authenticated identity — never from the request body, a query
    parameter, or anything else client-controllable. This uses the same
    trusted local-identity mechanism as get_principal (X-Local-Tenant,
    local/test only) rather than a real JWT claim: this codebase has no JWT
    validation infrastructure at all, and shipping a half-verified one would
    be worse than an honestly-scoped local mechanism. Real JWT-based tenant
    claims remain a pre-production gate, same as the rest of auth.

    _principal is required (not just imported) so tenant resolution always
    runs after identity authentication, never before or independently of it.
    """
    settings = _settings(request)
    if settings.app_env not in {"local", "test"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production identity provider is not configured",
        )
    if tenant is None or not tenant.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Local-Tenant header is required",
        )
    registry: TenantRegistry = request.app.state.tenant_registry
    try:
        bundle = registry.get(tenant.strip())
    except UnknownTenantError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TenantContext(tenant=tenant.strip(), bundle=bundle)


TenantScoped = Annotated[TenantContext, Depends(get_tenant_context)]


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


def enforce_demo_rate_limit(request: Request) -> None:
    """Rate-limit the browser demo routes by source IP.

    The demo routes deliberately accept no identity headers (browser forms
    cannot set custom headers), so `enforce_rate_limit`'s per-subject key
    does not apply here — without this, removing the deployment's IP
    allowlist would leave these two POST routes with no rate limiting at
    all. The `demo-ip:` prefix keeps this namespace disjoint from
    `enforce_rate_limit`'s subject-keyed entries in the same limiter
    instance, so a caller cannot collide the two by choosing an
    IP-shaped subject.
    """
    limiter: InMemoryRateLimiter = request.app.state.rate_limiter
    client_host = request.client.host if request.client else "unknown"
    limiter.check(f"demo-ip:{client_host}")
