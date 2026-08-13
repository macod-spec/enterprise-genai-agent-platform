"""Local-only authenticated Streamable HTTP MCP entry point."""

import os
from pathlib import Path
from typing import Literal, cast

from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary import JWTTokenVerifier
from enterprise_genai_platform.mcp_boundary.servers import (
    CustomerTools,
    PaymentTools,
    PolicyTools,
    create_remote_mcp,
)
from enterprise_genai_platform.rag import build_default_retriever


def main() -> None:
    domain_value = os.environ.get("MCP_DOMAIN", "customer")
    if domain_value not in {"customer", "payments", "policy"}:
        raise ValueError("MCP_DOMAIN must be customer, payments, or policy")
    domain = cast(Literal["customer", "payments", "policy"], domain_value)
    public_key_path = Path(os.environ["MCP_JWT_PUBLIC_KEY_FILE"]).resolve(strict=True)
    public_key = public_key_path.read_text(encoding="utf-8")
    issuer = os.environ["MCP_JWT_ISSUER"]
    resource_url = os.environ.get("MCP_RESOURCE_URL", "http://127.0.0.1:18100/mcp")
    verifier = JWTTokenVerifier(public_key, issuer=issuer, audience=resource_url)
    repository = NovaBankRepository()
    implementations = {
        "customer": CustomerTools(repository),
        "payments": PaymentTools(repository),
        "policy": PolicyTools(build_default_retriever()),
    }
    server = create_remote_mcp(
        domain,
        implementations[domain],
        verifier,
        issuer_url=issuer,
        resource_url=resource_url,
    )
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
