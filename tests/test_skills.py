"""Skill schema, governance, and API tests."""

import pytest
from fastapi.testclient import TestClient

from enterprise_genai_platform.gateway.app import create_app
from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.skills import SkillRegistry, build_default_skill_registry
from enterprise_genai_platform.skills.models import SkillDefinition


def test_default_registry_contains_governed_skills() -> None:
    registry = build_default_skill_registry()

    skills = registry.list_approved()

    assert [skill.name for skill in skills] == [
        "customer-profile",
        "payment-investigation",
        "policy-guidance",
    ]
    assert registry.get("payment-investigation", "1.0.0") is not None
    assert registry.get("missing", "1.0.0") is None


def test_registry_rejects_duplicate_and_unapproved_tools() -> None:
    valid = build_default_skill_registry().list_approved()[0]
    with pytest.raises(ValueError, match="Duplicate skill version"):
        SkillRegistry((valid, valid))

    invalid = SkillDefinition.model_validate(
        {**valid.model_dump(), "allowed_tools": ["system.shell"]}
    )
    with pytest.raises(ValueError, match="unapproved tool"):
        SkillRegistry((invalid,))


def test_skill_api_requires_platform_viewer_role() -> None:
    settings = Settings.model_validate({"app_env": "test"})
    client = TestClient(create_app(settings))

    denied = client.get(
        "/api/v1/skills",
        headers={"X-Local-User": "developer", "X-Local-Roles": "agent.invoke"},
    )
    allowed = client.get(
        "/api/v1/skills",
        headers={"X-Local-User": "developer", "X-Local-Roles": "platform.viewer"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert len(allowed.json()["skills"]) == 3
