"""Validated MCP input, output, caller, and audit contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CallerContext(Contract):
    subject: str = Field(min_length=1, max_length=128)
    roles: frozenset[str]
    agent: Literal["customer", "payments", "policy"]
    request_id: str = Field(min_length=1, max_length=128)


class CustomerRequest(Contract):
    customer_id: str = Field(pattern=r"^CUST-\d{4,10}$")


class TransactionRequest(Contract):
    transaction_id: str = Field(pattern=r"^TXN-\d{4,10}$")


class PolicySearchRequest(Contract):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=3, ge=1, le=5)


class CustomerRecord(Contract):
    customer_id: str
    display_name: str
    contact_preference: str
    masked_email: str
    classification: Literal["confidential-synthetic"]


class AccountRecord(Contract):
    account_id: str
    account_type: str
    status: str
    currency: str


class CustomerAccounts(Contract):
    customer_id: str
    accounts: tuple[AccountRecord, ...]


class TransactionRecord(Contract):
    transaction_id: str
    customer_id: str
    account_id: str
    amount: Decimal
    currency: str
    status: str
    payment_route: str
    failure_reason: str | None


class PolicyRecord(Contract):
    policy_id: str
    title: str
    text: str
    classification: Literal["internal-synthetic"]
    chunk_id: str
    version: str
    score: float
    provenance_sha256: str


class PolicySearchResults(Contract):
    policies: tuple[PolicyRecord, ...]


class AuditRecord(Contract):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request_id: str
    subject: str
    agent: str
    tool: str
    argument_fingerprint: str
    outcome: Literal["success", "denied", "invalid", "timeout", "error"]
    duration_ms: float = Field(ge=0)
    attempt_count: int = Field(ge=0)
