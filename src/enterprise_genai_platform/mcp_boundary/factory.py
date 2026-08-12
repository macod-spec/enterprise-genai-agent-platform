"""Construct the approved local MCP registry and tool gateway."""

from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary.contracts import (
    CallerContext,
    CustomerAccounts,
    CustomerRecord,
    CustomerRequest,
    PolicySearchRequest,
    PolicySearchResults,
    TransactionRecord,
    TransactionRequest,
)
from enterprise_genai_platform.mcp_boundary.gateway import GovernedMCPGateway, ToolRegistration
from enterprise_genai_platform.mcp_boundary.servers import CustomerTools, PaymentTools, PolicyTools
from enterprise_genai_platform.rag import AuthorizedRetriever, build_default_retriever


def build_local_mcp_gateway(
    repository: NovaBankRepository,
    *,
    retriever: AuthorizedRetriever | None = None,
    timeout_seconds: float = 2.0,
    max_attempts: int = 2,
    rate_limit: int = 30,
    rate_window_seconds: int = 60,
) -> GovernedMCPGateway:
    customer = CustomerTools(repository)
    payments = PaymentTools(repository)
    policy = PolicyTools(retriever or build_default_retriever())
    gateway = GovernedMCPGateway(
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        rate_limit=rate_limit,
        rate_window_seconds=rate_window_seconds,
    )

    async def get_customer(payload: CustomerRequest, _caller: CallerContext) -> CustomerRecord:
        return await customer.get_customer(payload.customer_id)

    async def get_accounts(payload: CustomerRequest, _caller: CallerContext) -> CustomerAccounts:
        return await customer.get_accounts(payload.customer_id)

    async def get_transaction(
        payload: TransactionRequest, _caller: CallerContext
    ) -> TransactionRecord:
        return await payments.get_transaction(payload.transaction_id)

    async def search_policy(
        payload: PolicySearchRequest, caller: CallerContext
    ) -> PolicySearchResults:
        return await policy.search(payload.query, caller.roles, payload.limit)

    gateway.register(
        ToolRegistration(
            name="customer.get_customer",
            allowed_agents=frozenset({"customer"}),
            required_roles=frozenset({"agent.invoke"}),
            input_model=CustomerRequest,
            output_model=CustomerRecord,
            handler=get_customer,
        )
    )
    gateway.register(
        ToolRegistration(
            name="customer.get_accounts",
            allowed_agents=frozenset({"customer"}),
            required_roles=frozenset({"agent.invoke"}),
            input_model=CustomerRequest,
            output_model=CustomerAccounts,
            handler=get_accounts,
        )
    )
    gateway.register(
        ToolRegistration(
            name="payments.get_transaction",
            allowed_agents=frozenset({"payments"}),
            required_roles=frozenset({"agent.invoke"}),
            input_model=TransactionRequest,
            output_model=TransactionRecord,
            handler=get_transaction,
        )
    )
    gateway.register(
        ToolRegistration(
            name="policy.search",
            allowed_agents=frozenset({"policy"}),
            required_roles=frozenset({"agent.invoke"}),
            input_model=PolicySearchRequest,
            output_model=PolicySearchResults,
            handler=search_policy,
        )
    )
    return gateway
