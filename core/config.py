from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # AI providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # LiteLLM
    litellm_master_key: str = "sk-finflow-master"
    primary_model: str = "claude-3-5-haiku-20241022"
    standard_model: str = "claude-3-5-sonnet-20241022"
    premium_model: str = "claude-opus-4-5-20251101"
    fallback_model: str = "gpt-4o-mini"

    # Langfuse observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: HttpUrl = "https://cloud.langfuse.com"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
