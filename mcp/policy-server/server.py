"""Local stdio entry point for the synthetic policy MCP server."""

from enterprise_genai_platform.mcp_boundary.servers import PolicyTools, create_policy_mcp
from enterprise_genai_platform.rag import build_default_retriever


def main() -> None:
    server = create_policy_mcp(PolicyTools(build_default_retriever()))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
