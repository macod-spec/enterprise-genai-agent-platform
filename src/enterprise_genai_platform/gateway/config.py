"""Typed gateway configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with secure production invariants."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Enterprise GenAI Agent Gateway"
    app_env: Literal["local", "test", "development", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_prefix: str = "/api/v1"
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_request_body_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    rate_limit_requests: int = Field(default=60, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    model_provider: Literal["mock"] = "mock"
    max_workflow_steps: int = Field(default=8, ge=1, le=50)
    model_gateway_provider: Literal["mock", "azure_openai"] = "mock"
    model_gateway_allowlist: list[str] = Field(default_factory=lambda: ["mock-deterministic"])
    model_gateway_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    model_gateway_max_attempts: int = Field(default=2, ge=1, le=3)
    model_gateway_daily_budget_gbp: float = Field(default=5.0, gt=0, le=10_000)
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    pii_protection_enabled: bool = True
    pii_mask_entities: list[str] = Field(
        default_factory=lambda: ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "IP_ADDRESS"]
    )
    pii_block_entities: list[str] = Field(
        default_factory=lambda: ["CREDIT_CARD", "IBAN_CODE", "US_SSN", "UK_SORT_CODE"]
    )
    pii_score_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    content_safety_enabled: bool = True
    content_safety_provider: Literal["mock", "azure"] = "mock"
    content_safety_endpoint: str | None = None
    content_safety_thresholds: dict[str, int] = Field(
        default_factory=lambda: {"Hate": 4, "SelfHarm": 4, "Sexual": 4, "Violence": 4}
    )
    rag_provider: Literal["local", "azure_search"] = "local"
    azure_search_endpoint: str | None = None
    azure_search_index_name: str = "novabank-policy-chunks"
    rag_synthesis_model: str = "mock-deterministic"
    rag_groundedness_minimum_term_overlap: float = Field(default=0.5, ge=0.0, le=1.0)
    mcp_tool_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    mcp_max_attempts: int = Field(default=2, ge=1, le=3)
    mcp_rate_limit: int = Field(default=30, ge=1, le=1_000)
    mcp_rate_window_seconds: int = Field(default=60, ge=1, le=3_600)
    state_database_path: str = Field(default=":memory:", min_length=1, max_length=500)
    state_backend: Literal["sqlite", "postgresql", "redis"] = "sqlite"
    state_connection_url: SecretStr | None = None
    otel_export_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4317"
    metrics_enabled: bool = True

    @model_validator(mode="after")
    def validate_security_boundaries(self) -> "Settings":
        """Reject permissive settings that are unsafe outside local development."""
        if "*" in self.cors_allowed_origins:
            raise ValueError("Wildcard CORS origins are not permitted")
        if not self.api_prefix.startswith("/"):
            raise ValueError("API_PREFIX must start with '/'")
        if self.state_backend != "sqlite" and self.state_connection_url is None:
            raise ValueError("STATE_CONNECTION_URL is required for PostgreSQL or Redis")
        if self.app_env in {"staging", "production"} and self.state_backend == "sqlite":
            raise ValueError("SQLite state is not permitted in staging or production")
        if self.model_gateway_provider == "azure_openai" and not self.azure_openai_endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT is required when MODEL_GATEWAY_PROVIDER=azure_openai"
            )
        if not self.model_gateway_allowlist:
            raise ValueError("MODEL_GATEWAY_ALLOWLIST must not be empty")
        if set(self.pii_mask_entities) & set(self.pii_block_entities):
            raise ValueError("An entity type cannot appear in both PII mask and block lists")
        if self.content_safety_provider == "azure" and not self.content_safety_endpoint:
            raise ValueError(
                "CONTENT_SAFETY_ENDPOINT is required when CONTENT_SAFETY_PROVIDER=azure"
            )
        if self.rag_provider == "azure_search" and not self.azure_search_endpoint:
            raise ValueError("AZURE_SEARCH_ENDPOINT is required when RAG_PROVIDER=azure_search")
        return self


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings once per process."""
    return Settings()
