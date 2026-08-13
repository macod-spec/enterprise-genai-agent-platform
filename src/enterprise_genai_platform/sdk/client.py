"""Bounded synchronous client for local and enterprise gateway integrations."""

from typing import Any, cast

import httpx


class AgentPlatformClient:
    def __init__(
        self,
        base_url: str,
        *,
        user: str,
        roles: frozenset[str],
        timeout_seconds: float = 30,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"X-Local-User": user, "X-Local-Roles": ",".join(sorted(roles))},
        )

    def investigate(self, query: str, *, request_id: str) -> dict[str, Any]:
        response = self._client.post(
            "/api/v1/workflows/investigate",
            json={"query": query},
            headers={"X-Request-ID": request_id},
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AgentPlatformClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
