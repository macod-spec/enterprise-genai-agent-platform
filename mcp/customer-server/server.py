"""Local stdio entry point for the synthetic customer MCP server."""

from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary.servers import CustomerTools, create_customer_mcp


def main() -> None:
    server = create_customer_mcp(CustomerTools(NovaBankRepository()))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
