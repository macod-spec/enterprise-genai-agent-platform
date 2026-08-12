"""Local stdio entry point for the synthetic payments MCP server."""

from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary.servers import PaymentTools, create_payments_mcp


def main() -> None:
    server = create_payments_mcp(PaymentTools(NovaBankRepository()))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
