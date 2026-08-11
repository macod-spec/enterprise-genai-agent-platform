"""Payments specialist with customer-transaction relationship checks."""

from enterprise_genai_platform.agents.base import AgentResult, Evidence
from enterprise_genai_platform.agents.parsing import customer_id_from, transaction_id_from
from enterprise_genai_platform.mcp_boundary.contracts import CallerContext, TransactionRecord
from enterprise_genai_platform.mcp_boundary.gateway import GovernedMCPGateway, MCPGatewayError


class PaymentsAgent:
    def __init__(self, gateway: GovernedMCPGateway) -> None:
        self._gateway = gateway

    async def investigate(self, query: str, caller: CallerContext) -> AgentResult:
        transaction_id = transaction_id_from(query)
        if transaction_id is None:
            return AgentResult(
                agent="payments",
                summary="A valid fictional transaction identifier is required.",
                error_code="TRANSACTION_ID_REQUIRED",
            )
        try:
            transaction = TransactionRecord.model_validate(
                await self._gateway.invoke(
                    "payments.get_transaction", {"transaction_id": transaction_id}, caller
                )
            )
        except MCPGatewayError:
            return AgentResult(
                agent="payments",
                summary="Payment tools could not return an authorised result.",
                requires_human_approval=True,
                error_code="PAYMENT_TOOL_FAILURE",
            )
        requested_customer = customer_id_from(query)
        if requested_customer and requested_customer != transaction.customer_id:
            return AgentResult(
                agent="payments",
                summary="The supplied customer and transaction identifiers do not match.",
                requires_human_approval=True,
                error_code="CUSTOMER_TRANSACTION_MISMATCH",
            )
        reason = transaction.failure_reason or "No failure reason recorded"
        return AgentResult(
            agent="payments",
            summary=(
                f"Transaction {transaction.transaction_id} is {transaction.status}; "
                "no payment action was executed."
            ),
            evidence=(
                Evidence(
                    source_id=transaction.transaction_id,
                    source_type="transaction",
                    detail=(
                        f"{transaction.currency} {transaction.amount:.2f} via "
                        f"{transaction.payment_route}; status {transaction.status}; "
                        f"reason: {reason}."
                    ),
                ),
            ),
        )
