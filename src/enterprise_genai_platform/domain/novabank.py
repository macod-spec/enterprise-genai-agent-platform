"""Read-only synthetic NovaBank data for local development and tests.

Every record in this module is fictional. Values must never be replaced with real
customer, account, transaction, or bank data.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class Customer:
    customer_id: str
    display_name: str
    contact_preference: str
    masked_email: str
    classification: Literal["confidential-synthetic"] = "confidential-synthetic"


@dataclass(frozen=True, slots=True)
class Account:
    account_id: str
    customer_id: str
    account_type: str
    status: str
    currency: str


@dataclass(frozen=True, slots=True)
class Transaction:
    transaction_id: str
    customer_id: str
    account_id: str
    amount: Decimal
    currency: str
    status: str
    payment_route: str
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class Policy:
    policy_id: str
    title: str
    text: str
    tags: frozenset[str]
    classification: Literal["internal-synthetic"] = "internal-synthetic"


_CUSTOMERS = (
    Customer("CUST-1098", "Avery Morgan", "email", "a***@example.test"),
    Customer("CUST-2042", "Jordan Ellis", "sms", "j***@example.test"),
)
_ACCOUNTS = (
    Account("ACCT-2001", "CUST-1098", "current", "active", "GBP"),
    Account("ACCT-2002", "CUST-1098", "savings", "active", "GBP"),
    Account("ACCT-3100", "CUST-2042", "current", "active", "GBP"),
)
_TRANSACTIONS = (
    Transaction(
        "TXN-5001",
        "CUST-1098",
        "ACCT-2001",
        Decimal("2500.00"),
        "GBP",
        "delayed",
        "Faster Payments",
        "Beneficiary bank acknowledgement timeout",
    ),
    Transaction(
        "TXN-5002",
        "CUST-1098",
        "ACCT-2001",
        Decimal("42.50"),
        "GBP",
        "completed",
        "Faster Payments",
        None,
    ),
    Transaction(
        "TXN-6100",
        "CUST-2042",
        "ACCT-3100",
        Decimal("125.00"),
        "GBP",
        "failed",
        "CHAPS",
        "Invalid beneficiary details",
    ),
)
_POLICIES = (
    Policy(
        "POL-PAY-001",
        "Delayed Faster Payments",
        "Confirm the payment status and beneficiary details. Allow two hours for a delayed "
        "acknowledgement before escalating to payment operations. Do not resend automatically.",
        frozenset({"payment", "delayed", "faster", "escalation"}),
    ),
    Policy(
        "POL-REF-002",
        "Refund approval",
        "Refunds above GBP 100 require an authorised operations officer to approve the action. "
        "The investigating agent may recommend but must not execute the refund.",
        frozenset({"refund", "approval", "limit", "human"}),
    ),
    Policy(
        "POL-DATA-003",
        "Customer data handling",
        "Return only the minimum customer data necessary for the task. Contact details must be "
        "masked in agent responses and audit records.",
        frozenset({"customer", "data", "privacy", "contact"}),
    ),
)


class NovaBankRepository:
    """Least-capability, read-only access to immutable synthetic records."""

    def get_customer(self, customer_id: str) -> Customer | None:
        return next((item for item in _CUSTOMERS if item.customer_id == customer_id), None)

    def get_customer_accounts(self, customer_id: str) -> tuple[Account, ...]:
        return tuple(item for item in _ACCOUNTS if item.customer_id == customer_id)

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        return next(
            (item for item in _TRANSACTIONS if item.transaction_id == transaction_id),
            None,
        )

    def search_policies(self, terms: frozenset[str], *, limit: int = 3) -> tuple[Policy, ...]:
        scored = sorted(
            ((len(policy.tags & terms), policy) for policy in _POLICIES),
            key=lambda item: (-item[0], item[1].policy_id),
        )
        return tuple(policy for score, policy in scored if score > 0)[:limit]
