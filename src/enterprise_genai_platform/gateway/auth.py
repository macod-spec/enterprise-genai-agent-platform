"""Authentication and authorization boundaries for gateway routes."""

import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.gateway.jwt_identity import (
    EntraIdentityResolver,
    JwtIdentity,
    JwtIdentityError,
)
from enterprise_genai_platform.gateway.principal import Principal
from enterprise_genai_platform.tenancy.context import TenantContext
from enterprise_genai_platform.tenancy.registry import TenantRegistry, UnknownTenantError

__all__ = [
    "AuthenticatedPrincipal",
    "InMemoryRateLimiter",
    "Principal",
    "TenantScoped",
    "enforce_demo_rate_limit",
    "enforce_rate_limit",
    "get_principal",
    "get_tenant_context",
    "require_roles",
]


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _jwt_configured(settings: Settings) -> bool:
    return bool(settings.jwt_jwks_uri and settings.jwt_issuer and settings.jwt_audience)


def _resolve_jwt_bearer(request: Request, authorization: str | None) -> None:
    """Verify the bearer token and cache (principal, tenant) on request.state.

    Cached rather than re-decoded: get_tenant_context depends on
    get_principal (below) and must not re-verify the same token a second
    time within one request.
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    resolver: EntraIdentityResolver = request.app.state.jwt_identity_resolver
    try:
        identity = resolver.resolve(token)
    except JwtIdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    request.state.jwt_identity = identity


def get_principal(
    request: Request,
    user: str | None = Header(default=None, alias="X-Local-User"),
    roles: str = Header(default="", alias="X-Local-Roles"),
    authorization: str | None = Header(default=None),
) -> Principal:
    """Authenticate the caller.

    local/test: the X-Local-* header mechanism, unchanged. Every other
    environment: a verified Entra-issued Bearer JWT
    (gateway/jwt_identity.py) if JWT settings are configured, else the same
    fail-closed 503 this endpoint has always returned outside local/test.
    """
    settings = _settings(request)
    if settings.app_env in {"local", "test"}:
        if user is None or not user.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Local identity header is required",
                headers={"WWW-Authenticate": "Local"},
            )
        normalized_roles = frozenset(role.strip() for role in roles.split(",") if role.strip())
        return Principal(subject=user.strip(), roles=normalized_roles)
    if not _jwt_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production identity provider is not configured",
        )
    _resolve_jwt_bearer(request, authorization)
    identity: JwtIdentity = request.state.jwt_identity
    return identity.principal


AuthenticatedPrincipal = Annotated[Principal, Depends(get_principal)]


def get_tenant_context(
    request: Request,
    _principal: AuthenticatedPrincipal,
    tenant: str | None = Header(default=None, alias="X-Local-Tenant"),
) -> TenantContext:
    """Resolve tenant exactly once, at the gateway edge, from the caller's
    authenticated identity — never from the request body, a query
    parameter, or anything else client-controllable.

    local/test: X-Local-Tenant, unchanged (this header has no meaning
    outside those two environments — see below). Every other environment:
    the tenant claim from the same verified Entra JWT get_principal already
    validated for this request, via gateway/jwt_identity.py. X-Local-Tenant
    is not read at all in that branch; a client cannot influence tenant
    resolution by setting it, only a validated App Role claim can.

    _principal is required (not just imported) so tenant resolution always
    runs after identity authentication, never before or independently of
    it — and, in JWT mode, so get_principal has already populated
    request.state.jwt_identity by the time this function's body runs.
    """
    settings = _settings(request)
    if settings.app_env in {"local", "test"}:
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
    if not _jwt_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production identity provider is not configured",
        )
    identity: JwtIdentity = request.state.jwt_identity
    registry = request.app.state.tenant_registry
    bundle = registry.get(identity.tenant)
    return TenantContext(tenant=identity.tenant, bundle=bundle)


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
