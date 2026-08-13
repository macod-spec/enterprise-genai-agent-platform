#!/usr/bin/env bash
# Zero-code-rule guard: onboarding a tenant means adding a file under
# config/tenants/, nothing else. Platform code (src/) must never hardcode a
# real tenant's name -- every tenant-scoped decision is made by reading the
# TenantBundle resolved from the caller's authenticated tenant claim, never
# by branching on which tenant is calling.
#
# Tenant names are read from config/tenants/*.yaml itself, not hardcoded
# here, so this check never needs editing when a tenant is added or
# removed -- editing this script for a routine onboarding would itself be
# exactly the code change the rule exists to prevent.
#
# Scoped to src/ only, not tests/: tests legitimately assert against real
# tenant bundles (the cross-tenant leakage suite, registry-loading tests,
# the Postgres RLS pool test) -- that is normal test practice, not drift.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tenants_dir="${repo_root}/config/tenants"

if ! compgen -G "${tenants_dir}"/*.y*ml >/dev/null; then
  echo "check-tenant-drift: no tenant bundles found under ${tenants_dir}" >&2
  exit 1
fi

tenant_names="$(grep -h '^name:' "${tenants_dir}"/*.y*ml | sed -E 's/^name:[[:space:]]*//')"
if [[ -z "${tenant_names}" ]]; then
  echo "check-tenant-drift: could not parse any tenant name from ${tenants_dir}" >&2
  exit 1
fi

pattern="$(echo "${tenant_names}" | paste -sd '|' -)"

if grep -rnE "${pattern}" "${repo_root}/src" --include="*.py"; then
  echo "" >&2
  echo "check-tenant-drift: platform code references a tenant name by" \
    "literal value (matches above)." >&2
  echo "Onboarding or changing a tenant must never require a src/ change --" \
    "read the tenant from the resolved TenantBundle/TenantContext instead." >&2
  exit 1
fi

echo "check-tenant-drift: no tenant-name drift found in src/ (checked against: $(echo "${tenant_names}" | tr '\n' ' '))"
