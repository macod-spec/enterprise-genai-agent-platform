"""Constrained identifier parsing shared by specialist agents."""

import re

_CUSTOMER_ID = re.compile(r"\bCUST-\d{4,10}\b", re.IGNORECASE)
_TRANSACTION_ID = re.compile(r"\bTXN-\d{4,10}\b", re.IGNORECASE)


def customer_id_from(query: str) -> str | None:
    match = _CUSTOMER_ID.search(query)
    return match.group(0).upper() if match else None


def transaction_id_from(query: str) -> str | None:
    match = _TRANSACTION_ID.search(query)
    return match.group(0).upper() if match else None
