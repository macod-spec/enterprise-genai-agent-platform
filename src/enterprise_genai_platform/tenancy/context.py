"""Immutable per-request tenant context.

Constructed exactly once, at the gateway edge, from the caller's
authenticated identity — never from anything else in the request. See
gateway/auth.py's get_tenant_context for where that resolution happens and
why nothing downstream may override it.
"""

from dataclasses import dataclass

from enterprise_genai_platform.tenancy.models import TenantBundle


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant: str
    bundle: TenantBundle
