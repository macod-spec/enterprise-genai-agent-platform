"""Load and validate tenant config bundles; fail startup on a bad one.

config/tenants/ lives at the repo root, not inside the installed package
(unlike skills/definitions/, which ships via importlib.resources) — tenant
bundles are operational configuration, not application code, and belong
next to infrastructure/ and docs/ rather than baked into the wheel. The
Dockerfile copies config/tenants/ into the runtime image explicitly so this
still resolves correctly in a container.
"""

from pathlib import Path

import yaml

from enterprise_genai_platform.tenancy.models import TenantBundle

DEFAULT_TENANT_CONFIG_DIR = Path("config/tenants")


class UnknownTenantError(ValueError):
    """Raised when a request references a tenant with no config bundle."""


class TenantRegistry:
    """Immutable, validated lookup from tenant name to its config bundle."""

    def __init__(self, bundles: tuple[TenantBundle, ...]) -> None:
        indexed: dict[str, TenantBundle] = {}
        for bundle in bundles:
            if bundle.name in indexed:
                raise ValueError(f"Duplicate tenant bundle: {bundle.name}")
            indexed[bundle.name] = bundle
        if not indexed:
            raise ValueError("Tenant registry must contain at least one bundle")
        self._bundles = indexed

    def get(self, name: str) -> TenantBundle:
        bundle = self._bundles.get(name)
        if bundle is None:
            raise UnknownTenantError(f"No config bundle for tenant {name!r}")
        return bundle

    def names(self) -> frozenset[str]:
        return frozenset(self._bundles)


def build_default_tenant_registry(
    config_dir: Path = DEFAULT_TENANT_CONFIG_DIR,
) -> TenantRegistry:
    if not config_dir.is_dir():
        raise ValueError(f"Tenant config directory does not exist: {config_dir}")
    bundles: list[TenantBundle] = []
    for resource in sorted(config_dir.iterdir(), key=lambda item: item.name):
        if resource.suffix not in {".yaml", ".yml"}:
            continue
        payload = yaml.safe_load(resource.read_text(encoding="utf-8"))
        try:
            bundles.append(TenantBundle.model_validate(payload))
        except Exception as exc:
            raise ValueError(f"Invalid tenant bundle {resource.name}: {exc}") from exc
    return TenantRegistry(tuple(bundles))
