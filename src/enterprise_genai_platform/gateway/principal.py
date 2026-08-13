"""Authenticated caller identity, shared by the local-header and JWT auth paths."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated caller identity supplied to agent platform services."""

    subject: str
    roles: frozenset[str]
