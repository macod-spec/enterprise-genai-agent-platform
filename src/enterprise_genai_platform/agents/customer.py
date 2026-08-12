"""Customer specialist with data-minimising responses."""

from enterprise_genai_platform.agents.base import AgentResult, Evidence
from enterprise_genai_platform.agents.parsing import customer_id_from
from enterprise_genai_platform.mcp_boundary.contracts import (
    CallerContext,
    CustomerAccounts,
    CustomerRecord,
)
from enterprise_genai_platform.mcp_boundary.gateway import GovernedMCPGateway, MCPGatewayError


class CustomerAgent:
    def __init__(self, gateway: GovernedMCPGateway) -> None:
        self._gateway = gateway

    async def investigate(self, query: str, caller: CallerContext) -> AgentResult:
        customer_id = customer_id_from(query)
        if customer_id is None:
            return AgentResult(
                agent="customer",
                summary="A valid fictional customer identifier is required.",
                error_code="CUSTOMER_ID_REQUIRED",
            )
        try:
            customer = CustomerRecord.model_validate(
                await self._gateway.invoke(
                    "customer.get_customer", {"customer_id": customer_id}, caller
                )
            )
            account_result = CustomerAccounts.model_validate(
                await self._gateway.invoke(
                    "customer.get_accounts", {"customer_id": customer_id}, caller
                )
            )
        except MCPGatewayError:
            return AgentResult(
                agent="customer",
                summary="Customer tools could not return an authorised result.",
                requires_human_approval=True,
                error_code="CUSTOMER_TOOL_FAILURE",
            )
        accounts = account_result.accounts
        evidence = (
            Evidence(
                source_id=customer.customer_id,
                source_type="customer",
                detail=(
                    f"Customer {customer.display_name}; preferred contact "
                    f"{customer.contact_preference}; "
                    f"masked email {customer.masked_email}."
                ),
            ),
            *(
                Evidence(
                    source_id=account.account_id,
                    source_type="account",
                    detail=(
                        f"{account.account_type} account is {account.status} in {account.currency}."
                    ),
                )
                for account in accounts
            ),
        )
        return AgentResult(
            agent="customer",
            summary=(
                f"Found synthetic customer {customer.customer_id} with {len(accounts)} accounts."
            ),
            evidence=tuple(evidence),
        )
