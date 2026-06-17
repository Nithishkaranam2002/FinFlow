from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, HttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.secrets import get_secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "FinFlow"
    app_env: str = "development"
    app_port: int = 8000
    secret_key: str = Field(default="change-me-in-production")
    debug: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    use_postgres_checkpointer: bool = False
    allow_registration: bool = True
    rate_limit_enabled: bool = True
    api_rate_limit_per_minute: int = 120
    login_rate_limit_per_minute: int = 10
    max_upload_size_bytes: int = 10 * 1024 * 1024
    stale_invoice_minutes: int = 30
    log_level: str = "info"
    auth_cookie_name: str = "finflow_access_token"
    sentry_dsn: str = ""
    metrics_enabled: bool = True

    # Object storage (S3 / MinIO)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "finflow"
    s3_secret_key: str = "finflow123"
    s3_bucket: str = "finflow-documents"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    # Secrets backend: env | aws
    secrets_backend: str = "env"
    aws_secrets_arn: str = ""

    # Database
    database_url: str = (
        "postgresql+asyncpg://finflow:finflow123@localhost:5432/finflow_db"
    )
    database_sync_url: str = (
        "postgresql://finflow:finflow123@localhost:5432/finflow_db"
    )

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # Temporal
    temporal_address: str = "localhost:7233"
    temporal_enabled: bool = True

    # AI providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # LiteLLM
    litellm_master_key: str = "sk-finflow-master"
    primary_model: str = "gpt-4o-mini"
    standard_model: str = "gpt-4o-mini"
    premium_model: str = "gpt-4o"
    fallback_model: str = "gpt-4o-mini"

    # Langfuse observability (LANGFUSE_BASE_URL is an alias for LANGFUSE_HOST)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: HttpUrl = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices(
            "LANGFUSE_HOST",
            "LANGFUSE_BASE_URL",
            "langfuse_host",
            "langfuse_base_url",
        ),
    )

    # Mem0
    mem0_api_key: str = ""

    # QuickBooks
    quickbooks_client_id: str = ""
    quickbooks_client_secret: str = ""
    quickbooks_sandbox: bool = True

    # Resend email
    resend_api_key: str = ""
    email_from: str = "noreply@finflow.dev"
    app_base_url: str = "http://localhost:8000"
    slack_webhook_url: str = ""

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # JWT auth
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    @field_validator("secret_key", mode="before")
    @classmethod
    def resolve_secret_key(cls, value: str | None) -> str:
        if not value or value == "change-me-in-production":
            return get_secret("SECRET_KEY", value or "change-me-in-production")
        return value

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def kafka_brokers(self) -> list[str]:
        return [
            broker.strip()
            for broker in self.kafka_bootstrap_servers.split(",")
            if broker.strip()
        ]

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @model_validator(mode="after")
    def apply_production_defaults(self) -> Settings:
        if self.is_production:
            if self.secret_key == "change-me-in-production":
                raise ValueError(
                    "SECRET_KEY must be set to a strong value when APP_ENV=production"
                )
            object.__setattr__(self, "debug", False)
            object.__setattr__(self, "use_postgres_checkpointer", True)
            object.__setattr__(self, "allow_registration", False)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
