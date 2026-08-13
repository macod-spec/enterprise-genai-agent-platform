"""Tenant config bundles: the schema-validated onboarding surface for new teams.

A new tenant is a file under config/tenants/, nothing else. Platform code
must never hardcode a tenant name (enforced by scripts/check-tenant-drift.sh
in CI); it only ever reads a TenantBundle resolved from a request's
authenticated tenant claim.
"""

from enterprise_genai_platform.tenancy.context import TenantContext
from enterprise_genai_platform.tenancy.models import MemoryPolicy, TenantBundle
from enterprise_genai_platform.tenancy.registry import (
    TenantRegistry,
    UnknownTenantError,
    build_default_tenant_registry,
)

__all__ = [
    "MemoryPolicy",
    "TenantBundle",
    "TenantContext",
    "TenantRegistry",
    "UnknownTenantError",
    "build_default_tenant_registry",
]
