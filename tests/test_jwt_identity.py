"""Entra-compatible JWT identity resolution tests (gateway/jwt_identity.py).

Verified against a synthetic RS256 keypair and a stubbed signing-key
lookup, not a real Entra tenant or network call — see the module docstring
in jwt_identity.py for why that split (implement + locally verify against a
faithful substitute, live-verify separately once real Entra App
Registration/App Roles exist) matches every other "requires real cloud
setup" gate in this project.
"""

import time
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from enterprise_genai_platform.gateway.jwt_identity import EntraIdentityResolver, JwtIdentityError
from enterprise_genai_platform.tenancy.registry import build_default_tenant_registry

_ISSUER = "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0"
_AUDIENCE = "api://novabank-agent-platform"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_WRONG_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _issue_token(
    *,
    roles: list[str],
    issuer: str = _ISSUER,
    audience: str = _AUDIENCE,
    exp_delta_seconds: int = 3600,
    signing_key: Any = _PRIVATE_KEY,
    subject: str | None = "alice@novabank.example",
    omit_claims: tuple[str, ...] = (),
) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": issuer,
        "aud": audience,
        "sub": "oid-alice-1234",
        "iat": now,
        "exp": now + exp_delta_seconds,
        "roles": roles,
    }
    if subject is not None:
        claims["preferred_username"] = subject
    for key in omit_claims:
        claims.pop(key, None)
    return jwt.encode(claims, signing_key, algorithm="RS256")


def _resolver() -> EntraIdentityResolver:
    registry = build_default_tenant_registry()
    stub_signing_key = SimpleNamespace(key=_PUBLIC_KEY)
    return EntraIdentityResolver(
        jwks_uri="https://login.microsoftonline.com/11111111.../discovery/v2.0/keys",
        issuer=_ISSUER,
        audience=_AUDIENCE,
        registry=registry,
        signing_key_resolver=lambda _token: stub_signing_key,
    )


def test_valid_token_resolves_principal_and_tenant_from_one_decode() -> None:
    token = _issue_token(roles=["agent.invoke", "payment-disputes"])

    identity = _resolver().resolve(token)

    assert identity.tenant == "payment-disputes"
    assert identity.principal.roles == frozenset({"agent.invoke"})
    assert identity.principal.subject == "alice@novabank.example"


def test_falls_back_to_oid_when_preferred_username_is_absent() -> None:
    token = _issue_token(roles=["payment-disputes"], subject=None)

    identity = _resolver().resolve(token)

    assert identity.principal.subject == "oid-alice-1234"


def test_rejects_a_token_signed_by_the_wrong_key() -> None:
    token = _issue_token(roles=["payment-disputes"], signing_key=_WRONG_PRIVATE_KEY)

    with pytest.raises(JwtIdentityError, match="invalid bearer token"):
        _resolver().resolve(token)


def test_rejects_an_expired_token() -> None:
    token = _issue_token(roles=["payment-disputes"], exp_delta_seconds=-60)

    with pytest.raises(JwtIdentityError, match="invalid bearer token"):
        _resolver().resolve(token)


def test_rejects_the_wrong_issuer() -> None:
    token = _issue_token(roles=["payment-disputes"], issuer="https://attacker.example/v2.0")

    with pytest.raises(JwtIdentityError, match="invalid bearer token"):
        _resolver().resolve(token)


def test_rejects_the_wrong_audience() -> None:
    token = _issue_token(roles=["payment-disputes"], audience="api://a-different-app")

    with pytest.raises(JwtIdentityError, match="invalid bearer token"):
        _resolver().resolve(token)


def test_rejects_a_token_with_no_tenant_role_at_all() -> None:
    token = _issue_token(roles=["agent.invoke", "platform.viewer"])

    with pytest.raises(JwtIdentityError, match="exactly one known tenant name"):
        _resolver().resolve(token)


def test_rejects_a_token_claiming_two_tenants_at_once() -> None:
    """An ambiguous tenant claim must fail closed, never be resolved by
    picking one — this is the multi-tenant analogue of a request that tries
    to set its own tenant via a second, conflicting source."""
    token = _issue_token(roles=["payment-disputes", "kyc-review"])

    with pytest.raises(JwtIdentityError, match="exactly one known tenant name"):
        _resolver().resolve(token)


def test_rejects_a_token_with_no_roles_claim() -> None:
    token = _issue_token(roles=[], omit_claims=("roles",))

    with pytest.raises(JwtIdentityError, match="exactly one known tenant name"):
        _resolver().resolve(token)


def test_constructor_requires_all_three_endpoint_settings() -> None:
    registry = build_default_tenant_registry()
    with pytest.raises(ValueError, match="required"):
        EntraIdentityResolver(jwks_uri="", issuer=_ISSUER, audience=_AUDIENCE, registry=registry)
