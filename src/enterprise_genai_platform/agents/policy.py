"""Policy specialist over a small immutable corpus; RAG replaces this later."""

from enterprise_genai_platform.agents.base import AgentResult, Evidence
from enterprise_genai_platform.mcp_boundary.contracts import CallerContext, PolicySearchResults
from enterprise_genai_platform.mcp_boundary.gateway import GovernedMCPGateway, MCPGatewayError


class PolicyAgent:
    def __init__(self, gateway: GovernedMCPGateway) -> None:
        self._gateway = gateway

    async def investigate(self, query: str, caller: CallerContext) -> AgentResult:
        try:
            search_result = PolicySearchResults.model_validate(
                await self._gateway.invoke("policy.search", {"query": query, "limit": 3}, caller)
            )
        except MCPGatewayError:
            return AgentResult(
                agent="policy",
                summary="Policy tools could not return an authorised result.",
                requires_human_approval=True,
                error_code="POLICY_TOOL_FAILURE",
            )
        policies = search_result.policies
        if not policies:
            return AgentResult(
                agent="policy",
                summary="No matching synthetic policy was found; manual review is required.",
                requires_human_approval=True,
                error_code="POLICY_NOT_FOUND",
            )
        return AgentResult(
            agent="policy",
            summary=f"Found {len(policies)} relevant synthetic policy record(s).",
            evidence=tuple(
                Evidence(
                    source_id=policy.policy_id,
                    source_type="policy",
                    detail=(
                        f"{policy.title}: {policy.text} "
                        f"[citation: {policy.chunk_id}, version {policy.version}, "
                        f"sha256 {policy.provenance_sha256}]"
                    ),
                )
                for policy in policies
            ),
        )
