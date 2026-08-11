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
        return self


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings once per process."""
    return Settings()
