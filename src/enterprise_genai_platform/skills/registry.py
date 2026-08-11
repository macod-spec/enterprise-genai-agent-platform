"""Immutable, validated, deny-by-default skill registry."""

from importlib.resources import files

import yaml

from enterprise_genai_platform.skills.models import SkillDefinition

_APPROVED_TOOLS = {
    "customer": frozenset({"customer.get_customer", "customer.get_accounts"}),
    "payments": frozenset({"payments.get_transaction"}),
    "policy": frozenset({"policy.search"}),
}


class SkillRegistry:
    def __init__(self, definitions: tuple[SkillDefinition, ...]) -> None:
        indexed: dict[str, SkillDefinition] = {}
        for definition in definitions:
            key = f"{definition.name}:{definition.version}"
            if key in indexed:
                raise ValueError(f"Duplicate skill version: {key}")
            if not set(definition.allowed_tools) <= _APPROVED_TOOLS[definition.agent]:
                raise ValueError(f"Skill requests an unapproved tool: {key}")
            indexed[key] = definition
        self._definitions = indexed

    def list_approved(self) -> tuple[SkillDefinition, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._definitions.values()
                    if item.governance_state == "approved"
                ),
                key=lambda item: (item.name, item.version),
            )
        )

    def get(self, name: str, version: str) -> SkillDefinition | None:
        definition = self._definitions.get(f"{name}:{version}")
        if definition is None or definition.governance_state != "approved":
            return None
        return definition


def build_default_skill_registry() -> SkillRegistry:
    directory = files("enterprise_genai_platform.skills").joinpath("definitions")
    definitions: list[SkillDefinition] = []
    for resource in sorted(directory.iterdir(), key=lambda item: item.name):
        if resource.name.endswith(".yaml"):
            payload = yaml.safe_load(resource.read_text(encoding="utf-8"))
            definitions.append(SkillDefinition.model_validate(payload))
    return SkillRegistry(tuple(definitions))
