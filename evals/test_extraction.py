"""DeepEval-backed extraction and fraud detection quality gates."""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase
from sqlalchemy import select

from core.database import async_session_factory
from evals.helpers.extraction_runner import run_extraction_on_golden
from evals.helpers.metrics import (
    compare_to_baseline,
    field_match_score,
    format_pr_comment,
    load_baseline,
    write_eval_report,
)
from models.invoice import Invoice
from services.fraud_detection import run_fraud_checks

EVALS_ROOT = Path(__file__).resolve().parent
REPORT_PATH = EVALS_ROOT / "reports" / "extraction_report.json"

FIELD_ACCURACY_THRESHOLD = 0.90
CONFIDENCE_CALIBRATION_THRESHOLD = 1.0
DUPLICATE_DETECTION_THRESHOLD = 1.0
THRESHOLD_GAMING_THRESHOLD = 1.0


class FieldAccuracyMetric(BaseMetric):
    async_mode = False

    def __init__(self, threshold: float = FIELD_ACCURACY_THRESHOLD):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        expected = json.loads(test_case.expected_output or "{}")
        actual = json.loads(test_case.actual_output or "{}")
        self.score = field_match_score(expected, actual)
        self.success = self.score >= self.threshold
        self.reason = f"Field accuracy {self.score:.1%} (threshold {self.threshold:.0%})"
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Field Accuracy"


class AggregateThresholdMetric(BaseMetric):
    async_mode = False

    def __init__(self, threshold: float, label: str = "Aggregate Metric"):
        self.threshold = threshold
        self.label = label
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        self.score = float(test_case.actual_output or "0")
        self.success = self.score >= self.threshold
        self.reason = f"{self.label}: {self.score:.1%} vs {self.threshold:.0%}"
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return self.label


@pytest.fixture(scope="module")
def use_live_llm(llm_credentials_available: bool) -> bool:
    if os.getenv("FINFLOW_EVAL_FORCE_LIVE") == "1":
        if not llm_credentials_available:
            pytest.fail("FINFLOW_EVAL_FORCE_LIVE=1 but no LLM API credentials found")
        return True
    return llm_credentials_available


@pytest.mark.asyncio
async def test_field_accuracy_test(golden_invoices, baseline_metrics, use_live_llm):
    scores: list[float] = []
    for row in golden_invoices["invoices"]:
        extracted, _overall, _scores = await run_extraction_on_golden(
            row,
            use_live_llm=use_live_llm,
        )
        case = LLMTestCase(
            input=row["pdf_text"][:500],
            actual_output=json.dumps(extracted),
            expected_output=json.dumps(row["expected"]),
        )
        metric = FieldAccuracyMetric(threshold=FIELD_ACCURACY_THRESHOLD)
        scores.append(metric.measure(case))

    field_accuracy = round(sum(scores) / len(scores), 4) if scores else 0.0
    aggregate = AggregateThresholdMetric(
        threshold=FIELD_ACCURACY_THRESHOLD,
        label="Field Accuracy",
    )
    assert_test(
        LLMTestCase(
            input="golden-invoice-set",
            actual_output=str(field_accuracy),
            expected_output=str(FIELD_ACCURACY_THRESHOLD),
        ),
        [aggregate],
    )

    report = {
        "suite": "extraction",
        "metrics": {"field_accuracy": field_accuracy},
        "sample_count": len(scores),
        "mode": "live_llm" if use_live_llm else "deterministic_fallback",
    }
    write_eval_report(REPORT_PATH, report)

    baseline_value = float(baseline_metrics["field_accuracy"])
    assert field_accuracy >= baseline_value, (
        f"field_accuracy {field_accuracy:.1%} below baseline {baseline_value:.1%}"
    )


@pytest.mark.asyncio
async def test_confidence_calibration_test(golden_invoices, baseline_metrics, use_live_llm):
    messy_rows = [
        row
        for row in golden_invoices["invoices"]
        if row.get("messy_flags") or row.get("category") == "messy"
    ]
    assert messy_rows, "Expected messy invoices in golden set"

    passes = 0
    for row in messy_rows:
        _extracted, overall, _scores = await run_extraction_on_golden(
            row,
            use_live_llm=use_live_llm,
        )
        if overall < 0.75:
            passes += 1

    calibration_rate = round(passes / len(messy_rows), 4)
    aggregate = AggregateThresholdMetric(
        threshold=float(baseline_metrics["confidence_calibration_rate"]),
        label="Confidence Calibration",
    )
    assert_test(
        LLMTestCase(
            input="messy-invoice-set",
            actual_output=str(calibration_rate),
            expected_output=str(baseline_metrics["confidence_calibration_rate"]),
        ),
        [aggregate],
    )
    assert calibration_rate >= 0.85


@pytest.mark.asyncio
async def test_duplicate_detection_test(golden_invoices, baseline_metrics):
    pairs = golden_invoices["duplicate_pairs"][:15]
    assert len(pairs) >= 15, "Expected at least 15 duplicate pairs in golden set"

    detected = 0
    async with async_session_factory() as session:
        for pair in pairs:
            target = await session.get(Invoice, uuid.UUID(pair["target_invoice_id"]))
            source = await session.get(Invoice, uuid.UUID(pair["source_invoice_id"]))
            if not target or not source:
                pytest.skip("Synthetic invoices not seeded in database")

            target.created_at = datetime.now(timezone.utc)
            source.created_at = datetime.now(timezone.utc)
            await session.flush()

            result = await run_fraud_checks(
                session,
                tenant_id=target.tenant_id,
                invoice_id=target.id,
                vendor_id=target.vendor_id,
                invoice_number=target.invoice_number,
                amount=target.amount,
                invoice_date=target.due_date or date.today(),
            )
            flag_types = {flag["type"] for flag in result.fraud_flags}
            if "POTENTIAL_DUPLICATE" in flag_types:
                detected += 1
        await session.commit()

    detection_rate = round(detected / len(pairs), 4)
    aggregate = AggregateThresholdMetric(
        threshold=DUPLICATE_DETECTION_THRESHOLD,
        label="Duplicate Detection",
    )
    assert_test(
        LLMTestCase(
            input="duplicate-pairs",
            actual_output=str(detection_rate),
            expected_output=str(DUPLICATE_DETECTION_THRESHOLD),
        ),
        [aggregate],
    )

    if REPORT_PATH.exists():
        with REPORT_PATH.open(encoding="utf-8") as handle:
            report = json.load(handle)
    else:
        report = {"suite": "extraction", "metrics": {}}
    report["metrics"]["duplicate_detection_rate"] = detection_rate
    write_eval_report(REPORT_PATH, report)


@pytest.mark.asyncio
async def test_threshold_gaming_test(golden_invoices, baseline_metrics):
    threshold_rows = golden_invoices["threshold_invoices"][:5]
    assert len(threshold_rows) >= 5, "Expected at least 5 threshold-gaming invoices"

    detected = 0
    async with async_session_factory() as session:
        for row in threshold_rows:
            invoice = await session.get(Invoice, uuid.UUID(row["invoice_id"]))
            if not invoice:
                pytest.skip("Synthetic invoices not seeded in database")

            result = await run_fraud_checks(
                session,
                tenant_id=invoice.tenant_id,
                invoice_id=invoice.id,
                vendor_id=invoice.vendor_id,
                invoice_number=invoice.invoice_number,
                amount=Decimal(str(row["amount"])),
                invoice_date=invoice.due_date or date.today(),
            )
            flag_types = {flag["type"] for flag in result.fraud_flags}
            if "THRESHOLD_GAMING" in flag_types:
                detected += 1

    detection_rate = round(detected / len(threshold_rows), 4)
    aggregate = AggregateThresholdMetric(
        threshold=THRESHOLD_GAMING_THRESHOLD,
        label="Threshold Gaming Detection",
    )
    assert_test(
        LLMTestCase(
            input="threshold-gaming-invoices",
            actual_output=str(detection_rate),
            expected_output=str(THRESHOLD_GAMING_THRESHOLD),
        ),
        [aggregate],
    )

    if REPORT_PATH.exists():
        with REPORT_PATH.open(encoding="utf-8") as handle:
            report = json.load(handle)
    else:
        report = {"suite": "extraction", "metrics": {}}
    report["metrics"]["threshold_gaming_detection_rate"] = detection_rate
    write_eval_report(REPORT_PATH, report)


def test_write_extraction_pr_comment(baseline_metrics):
    if not REPORT_PATH.exists():
        pytest.skip("Extraction report not generated yet")
    with REPORT_PATH.open(encoding="utf-8") as handle:
        report = json.load(handle)
    comment = format_pr_comment(report, baseline_metrics)
    assert "Field Accuracy" in comment
    comparisons = compare_to_baseline(report["metrics"], baseline_metrics)
    assert "field_accuracy" in comparisons
