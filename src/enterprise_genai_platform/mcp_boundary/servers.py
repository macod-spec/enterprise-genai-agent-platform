"""Official MCP SDK server definitions over synthetic NovaBank services."""

from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary.contracts import (
    AccountRecord,
    CustomerAccounts,
    CustomerRecord,
    PolicyRecord,
    PolicySearchResults,
    TransactionRecord,
)
from enterprise_genai_platform.rag import AuthorizedRetriever


class CustomerTools:
    def __init__(self, repository: NovaBankRepository) -> None:
        self._repository = repository

    async def get_customer(self, customer_id: str) -> CustomerRecord:
        customer = self._repository.get_customer(customer_id)
        if customer is None:
            raise LookupError("customer not found")
        return CustomerRecord(
            customer_id=customer.customer_id,
            display_name=customer.display_name,
            contact_preference=customer.contact_preference,
            masked_email=customer.masked_email,
            classification=customer.classification,
        )

    async def get_accounts(self, customer_id: str) -> CustomerAccounts:
        accounts = self._repository.get_customer_accounts(customer_id)
        return CustomerAccounts(
            customer_id=customer_id,
            accounts=tuple(
                AccountRecord(
                    account_id=account.account_id,
                    account_type=account.account_type,
                    status=account.status,
                    currency=account.currency,
                )
                for account in accounts
            ),
        )


class PaymentTools:
    def __init__(self, repository: NovaBankRepository) -> None:
        self._repository = repository

    async def get_transaction(self, transaction_id: str) -> TransactionRecord:
        transaction = self._repository.get_transaction(transaction_id)
        if transaction is None:
            raise LookupError("transaction not found")
        return TransactionRecord(
            transaction_id=transaction.transaction_id,
            customer_id=transaction.customer_id,
            account_id=transaction.account_id,
            amount=transaction.amount,
            currency=transaction.currency,
            status=transaction.status,
            payment_route=transaction.payment_route,
            failure_reason=transaction.failure_reason,
        )


class PolicyTools:
    def __init__(self, retriever: AuthorizedRetriever) -> None:
        self._retriever = retriever

    async def search(
        self,
        query: str,
        caller_roles: frozenset[str],
        limit: int = 3,
    ) -> PolicySearchResults:
        retrieval = self._retriever.retrieve(query, caller_roles=caller_roles, limit=limit)
        return PolicySearchResults(
            policies=tuple(
                PolicyRecord(
                    policy_id=hit.citation.document_id,
                    title=hit.citation.title,
                    text=hit.text,
                    classification="internal-synthetic",
                    chunk_id=hit.citation.chunk_id,
                    version=hit.citation.version,
                    score=hit.score,
                    provenance_sha256=hit.citation.provenance_sha256,
                )
                for hit in retrieval.hits
            )
        )


def create_customer_mcp(tools: CustomerTools) -> FastMCP:
    server = FastMCP("novabank-customer", json_response=True)
    server.tool(name="customer.get_customer")(tools.get_customer)
    server.tool(name="customer.get_accounts")(tools.get_accounts)
    return server


def create_payments_mcp(tools: PaymentTools) -> FastMCP:
    server = FastMCP("novabank-payments", json_response=True)
    server.tool(name="payments.get_transaction")(tools.get_transaction)
    return server


def create_policy_mcp(tools: PolicyTools) -> FastMCP:
    server = FastMCP("novabank-policy", json_response=True)

    async def search(query: str, limit: int = 3) -> PolicySearchResults:
        """Schema-only local tool; governed callers receive roles through the gateway."""
        return await tools.search(query, frozenset(), limit)

    server.tool(name="policy.search")(search)
    return server


def create_remote_mcp(
    name: str,
    tools: CustomerTools | PaymentTools | PolicyTools,
    token_verifier: TokenVerifier,
    *,
    issuer_url: str,
    resource_url: str,
) -> FastMCP:
    """Create a stateless, authenticated, loopback-only MCP domain server."""
    scope = f"mcp:{name}"
    server = FastMCP(
        f"novabank-{name}",
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer_url),
            resource_server_url=AnyHttpUrl(resource_url),
            required_scopes=[scope],
        ),
        host="127.0.0.1",
        json_response=True,
        stateless_http=True,
        max_request_body_size=1_048_576,
    )
    if name == "customer" and isinstance(tools, CustomerTools):
        server.tool(name="customer.get_customer")(tools.get_customer)
        server.tool(name="customer.get_accounts")(tools.get_accounts)
    elif name == "payments" and isinstance(tools, PaymentTools):
        server.tool(name="payments.get_transaction")(tools.get_transaction)
    elif name == "policy" and isinstance(tools, PolicyTools):

        async def search(query: str, limit: int = 3) -> PolicySearchResults:
            return await tools.search(query, frozenset({"agent.invoke"}), limit)

        server.tool(name="policy.search")(search)
    else:
        raise ValueError("MCP server name and tool implementation do not match")
    return server
