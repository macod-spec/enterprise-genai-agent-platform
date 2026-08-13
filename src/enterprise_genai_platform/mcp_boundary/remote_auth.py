"""Strict JWT verification for remote MCP resource servers."""

from collections.abc import Collection
from typing import Any

import jwt
from mcp.server.auth.provider import AccessToken


class JWTTokenVerifier:
    """Verify short-lived asymmetric access tokens without retaining credentials."""

    def __init__(self, public_key_pem: str, *, issuer: str, audience: str) -> None:
        if not public_key_pem.strip() or not issuer.startswith("https://"):
            raise ValueError("A public key and HTTPS issuer are required")
        self._public_key = public_key_pem
        self._issuer = issuer
        self._audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]},
            )
            scopes = _parse_scopes(claims.get("scope"))
            subject = claims["sub"]
            client_id = claims.get("client_id", subject)
            if not isinstance(subject, str) or not subject or not isinstance(client_id, str):
                return None
            return AccessToken(
                token=token,
                client_id=client_id,
                scopes=scopes,
                expires_at=int(claims["exp"]),
                resource=self._audience,
                subject=subject,
                claims={"jti": claims["jti"]},
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            return None


def _parse_scopes(value: object) -> list[str]:
    if isinstance(value, str):
        scopes: Collection[object] = value.split()
    elif isinstance(value, list):
        scopes = value
    else:
        return []
    validated = [scope for scope in scopes if isinstance(scope, str) and 0 < len(scope) <= 128]
    return sorted(set(validated))[:50]
