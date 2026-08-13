"""Entra-compatible JWT verification for production caller and tenant identity.

Local/test environments use the X-Local-* headers (gateway/auth.py); every
other environment requires a real Bearer JWT verified here instead. This is
the replacement for the local-header trust model flagged in
docs/portfolio/limitations.md: X-Local-Tenant is a client-supplied value
with nothing checking it against the caller's real identity, so every
isolation control built on top of it (RLS, retrieval filtering, budget,
metrics) only isolates tenants from each other once a tenant is decided --
none of it stops a caller from deciding to be a tenant it isn't. Verifying
the token this module resolves closes exactly that gap.

Caller identity and tenant are resolved from the *same* validated token in
one decode, not two independent checks: a real Entra deployment would never
trust caller identity from one place and tenant from another. Entra has no
native "business tenant" concept distinct from the Entra directory tenant
(`tid`), so this platform's tenant is carried as an Entra App Role (the
`roles` claim) -- whichever role names in the token happen to match a name
already declared in config/tenants/*.yaml is the caller's tenant; every
other role value in the same claim is treated as a platform capability role,
identical in meaning to the existing X-Local-Roles vocabulary
(`agent.invoke`, `platform.viewer`, ...). A token must carry exactly one
tenant-matching role -- zero or more than one fails closed, since an
ambiguous tenant claim must never be resolved by guessing.

Signing keys are fetched from the issuer's JWKS endpoint and selected by the
token's `kid` header (`jwt.PyJWKClient`, which also caches and refreshes),
not a single pinned public key -- Entra rotates its signing keys routinely,
and a static key (the pattern `mcp_boundary/remote_auth.py` uses for the
narrower remote-MCP-transport case) would silently start rejecting every
token the day Entra rotates.

Implemented and verified against synthetic RS256 keys and a stubbed JWKS
lookup (tests/test_jwt_identity.py) -- not yet live-verified against a real
Entra tenant, which needs a real App Registration with App Roles defined and
assigned, a separate Azure AD administrative decision (see
docs/portfolio/live-verification.md for how every other "requires real
cloud setup" gate in this project has been handled: implement, verify
locally against a faithful substitute, then live-verify separately once
that setup exists).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from enterprise_genai_platform.gateway.principal import Principal
from enterprise_genai_platform.tenancy.registry import TenantRegistry


@dataclass(frozen=True, slots=True)
class JwtIdentity:
    principal: Principal
    tenant: str


class JwtIdentityError(Exception):
    """The bearer token failed signature/claim verification or tenant resolution."""


class EntraIdentityResolver:
    """Resolve caller identity and tenant from a verified Entra-issued JWT."""

    def __init__(
        self,
        *,
        jwks_uri: str,
        issuer: str,
        audience: str,
        registry: TenantRegistry,
        tenant_claim: str = "roles",
        signing_key_resolver: Callable[[str], Any] | None = None,
    ) -> None:
        """signing_key_resolver overrides how a signing key is obtained from
        a raw token, taking the token and returning an object with a `.key`
        attribute (matching jwt.PyJWK's shape). Defaults to a real
        PyJWKClient's get_signing_key_from_jwt (fetches and caches the
        issuer's real JWKS, selecting by the token's `kid` header). Tests
        inject a stub here instead of reaching the network or requiring a
        real Entra tenant.
        """
        if not jwks_uri or not issuer or not audience:
            raise ValueError("jwks_uri, issuer, and audience are all required")
        self._issuer = issuer
        self._audience = audience
        self._registry = registry
        self._tenant_claim = tenant_claim
        self._get_signing_key = (
            signing_key_resolver
            or PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600).get_signing_key_from_jwt
        )

    def resolve(self, bearer_token: str) -> JwtIdentity:
        try:
            signing_key = self._get_signing_key(bearer_token)
            claims = jwt.decode(
                bearer_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise JwtIdentityError(f"invalid bearer token: {exc}") from exc

        claimed_roles = self._extract_role_list(claims.get(self._tenant_claim))
        known_tenants = frozenset(self._registry.names())
        tenant_matches = claimed_roles & known_tenants
        if len(tenant_matches) != 1:
            raise JwtIdentityError(
                f"token {self._tenant_claim!r} claim must contain exactly one known "
                f"tenant name; found {sorted(tenant_matches)}"
            )
        tenant_name = next(iter(tenant_matches))
        platform_roles = claimed_roles - tenant_matches

        subject = claims.get("preferred_username") or claims.get("oid") or claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise JwtIdentityError("token carries no usable subject claim")

        return JwtIdentity(
            principal=Principal(subject=subject, roles=platform_roles),
            tenant=tenant_name,
        )

    @staticmethod
    def _extract_role_list(value: object) -> frozenset[str]:
        if isinstance(value, str):
            candidates: list[object] = [value]
        elif isinstance(value, list):
            candidates = value
        else:
            return frozenset()
        return frozenset(item for item in candidates if isinstance(item, str) and item)
