"""Shared pytest fixtures for FinFlow evaluation suite."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

EVALS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_ROOT.parent
GOLDEN_INVOICES_PATH = EVALS_ROOT / "golden_invoices" / "golden_invoices.json"
GOLDEN_RECONCILIATION_PATH = EVALS_ROOT / "golden_reconciliation" / "golden_reconciliation.json"
BASELINE_PATH = EVALS_ROOT / "baseline.json"
SYNTHETIC_DATA_PATH = PROJECT_ROOT / "data" / "synthetic_data.json"


def _has_llm_credentials() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def golden_invoices() -> dict:
    if not GOLDEN_INVOICES_PATH.exists():
        pytest.skip(
            f"Golden invoice set missing at {GOLDEN_INVOICES_PATH}. "
            "Run: uv run python evals/golden_invoices/generate_golden_set.py"
        )
    with GOLDEN_INVOICES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def golden_reconciliation() -> dict:
    if not GOLDEN_RECONCILIATION_PATH.exists():
        pytest.skip(
            f"Golden reconciliation set missing at {GOLDEN_RECONCILIATION_PATH}. "
            "Run: uv run python evals/golden_reconciliation/generate_golden_pairs.py"
        )
    with GOLDEN_RECONCILIATION_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def baseline_metrics() -> dict:
    with BASELINE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def llm_credentials_available() -> bool:
    return _has_llm_credentials()


@pytest.fixture(scope="session")
def synthetic_data_available() -> bool:
    return SYNTHETIC_DATA_PATH.exists()
