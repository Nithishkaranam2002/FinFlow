import pytest
from pydantic import ValidationError

from core.config import Settings


def test_production_requires_strong_secret_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me-in-production")

    with pytest.raises(ValidationError):
        Settings()


def test_production_disables_open_registration(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "production-secret-key-with-enough-entropy")

    settings = Settings()

    assert settings.allow_registration is False
    assert settings.use_postgres_checkpointer is True
    assert settings.debug is False


def test_development_allows_registration_by_default(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")

    settings = Settings()

    assert settings.allow_registration is True
