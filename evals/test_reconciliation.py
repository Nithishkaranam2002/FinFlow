"""DeepEval-backed reconciliation pipeline quality gates."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

from agents.reconciliation_agent import run_reconciliation_pipeline
from evals.helpers.metrics import compare_to_baseline, format_pr_comment, load_baseline, write_eval_report
from evals.helpers.reconciliation_fixtures import (
    collect_reconciliation_results,
    setup_reconciliation_eval_dataset,
)

EVALS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_ROOT.parent
SYNTHETIC_PATH = PROJECT_ROOT / "data" / "synthetic_data.json"
REPORT_PATH = EVALS_ROOT / "reports" / "reconciliation_report.json"

MATCH_RATE_THRESHOLD = 0.85
EXACT_FUZZY_THRESHOLD = 0.60
LLM_REASONING_THRESHOLD = 0.80


class ReconciliationAccuracyMetric(BaseMetric):
    async_mode = False

    def __init__(self, threshold: float):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        self.score = float(test_case.actual_output or "0")
        self.success = self.score >= self.threshold
        self.reason = f"Rate {self.score:.1%} vs threshold {self.threshold:.0%}"
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Reconciliation Accuracy"


class LLMReasoningQualityMetric(BaseMetric):
    async_mode = False

    def __init__(self, threshold: float = LLM_REASONING_THRESHOLD):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        explanation = (test_case.actual_output or "").strip()
        bank_line = test_case.input or ""
        if not explanation:
            self.score = 0.0
        elif explanation.lower().startswith("could not match"):
            self.score = 0.0
        else:
            tokens = re.findall(r"[A-Za-z0-9]{4,}", bank_line)
            hits = sum(1 for token in tokens[:6] if token.lower() in explanation.lower())
            self.score = 1.0 if hits >= 1 and len(explanation) >= 40 else 0.0
        self.success = self.score >= self.threshold
        self.reason = f"Explanation specificity score {self.score:.0f}"
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "LLM Reasoning Quality"


@pytest.fixture(scope="module")
def synthetic_invoices() -> list[dict]:
    if not SYNTHETIC_PATH.exists():
        pytest.skip("Synthetic data missing")
    with SYNTHETIC_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)["invoices"]


@pytest.mark.asyncio
async def test_reconciliation_accuracy(golden_reconciliation, baseline_metrics, synthetic_invoices):
    statement_id, tenant_id = await setup_reconciliation_eval_dataset(
        golden_reconciliation,
        synthetic_invoices,
    )

    await run_reconciliation_pipeline(statement_id=statement_id, tenant_id=tenant_id)
    results = await collect_reconciliation_results(statement_id, tenant_id)

    match_case = LLMTestCase(
        input=f"statement:{statement_id}",
        actual_output=str(results["match_rate"]),
        expected_output=str(MATCH_RATE_THRESHOLD),
    )
    assert_test(match_case, [ReconciliationAccuracyMetric(MATCH_RATE_THRESHOLD)])

    exact_fuzzy_case = LLMTestCase(
        input=f"statement:{statement_id}",
        actual_output=str(results["exact_fuzzy_rate"]),
        expected_output=str(EXACT_FUZZY_THRESHOLD),
    )
    assert_test(exact_fuzzy_case, [ReconciliationAccuracyMetric(EXACT_FUZZY_THRESHOLD)])

    report = {
        "suite": "reconciliation",
        "metrics": {
            "reconciliation_match_rate": round(results["match_rate"], 4),
            "exact_fuzzy_match_rate": round(results["exact_fuzzy_rate"], 4),
        },
        "counts": {
            "total_lines": results["total_lines"],
            "matched_lines": results["matched_lines"],
            "exact_matched": results["exact_matched"],
            "fuzzy_matched": results["fuzzy_matched"],
            "llm_matched": results["llm_matched"],
        },
    }
    write_eval_report(REPORT_PATH, report)

    assert results["match_rate"] >= float(baseline_metrics["reconciliation_match_rate"])
    assert results["match_rate"] >= MATCH_RATE_THRESHOLD
    assert results["exact_fuzzy_rate"] >= float(baseline_metrics["exact_fuzzy_match_rate"])
    assert results["exact_fuzzy_rate"] >= EXACT_FUZZY_THRESHOLD


@pytest.mark.asyncio
async def test_llm_reasoning_quality(golden_reconciliation, baseline_metrics, synthetic_invoices):
    statement_id, tenant_id = await setup_reconciliation_eval_dataset(
        golden_reconciliation,
        synthetic_invoices,
    )
    await run_reconciliation_pipeline(statement_id=statement_id, tenant_id=tenant_id)
    results = await collect_reconciliation_results(statement_id, tenant_id)

    unmatched = results["unmatched_lines"]
    if not unmatched:
        pytest.skip("No unmatched lines to evaluate reasoning quality")

    quality_scores: list[float] = []
    for line in unmatched:
        explanation = line.llm_explanation or line.exception_reason or ""
        bank_context = f"{line.description} {line.reference or ''} {line.amount} {line.transaction_date}"
        case = LLMTestCase(input=bank_context, actual_output=explanation, expected_output="specific")
        metric = LLMReasoningQualityMetric(threshold=LLM_REASONING_THRESHOLD)
        assert_test(case, [metric])
        quality_scores.append(metric.score)

    quality_rate = round(sum(quality_scores) / len(quality_scores), 4)
    assert quality_rate >= float(baseline_metrics["llm_reasoning_quality_rate"])
    assert quality_rate >= LLM_REASONING_THRESHOLD


def test_write_reconciliation_pr_comment(baseline_metrics):
    if not REPORT_PATH.exists():
        pytest.skip("Reconciliation report not generated yet")
    with REPORT_PATH.open(encoding="utf-8") as handle:
        report = json.load(handle)
    comment = format_pr_comment(report, baseline_metrics)
    assert "Reconciliation Match Rate" in comment
    comparisons = compare_to_baseline(report["metrics"], baseline_metrics)
    assert "reconciliation_match_rate" in comparisons
