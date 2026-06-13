"""Fast unit tests for FinFlow (no LLM / external services required)."""

from __future__ import annotations

import pytest

from core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
