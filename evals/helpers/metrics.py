"""Metric helpers and baseline comparison for eval results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

EVALS_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = EVALS_ROOT / "baseline.json"


def normalize_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    cleaned = str(value).replace(",", "").replace("$", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except Exception:
        return None


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"tbd", "net 30", "end of month"}:
        return None
    return text[:10]


def field_match_score(expected: dict[str, Any], actual: dict[str, Any]) -> float:
    scores: list[float] = []

    expected_amount = normalize_amount(expected.get("total_amount"))
    actual_amount = normalize_amount(actual.get("total_amount") or actual.get("amount"))
    if expected_amount is None and actual_amount is None:
        scores.append(1.0)
    elif expected_amount is not None and actual_amount is not None:
        scores.append(1.0 if expected_amount == actual_amount else 0.0)
    else:
        scores.append(0.0)

    expected_vendor = str(expected.get("vendor_name") or "").strip()
    actual_vendor = str(actual.get("vendor_name") or "").strip()
    if expected_vendor and actual_vendor:
        scores.append(fuzz.token_sort_ratio(expected_vendor, actual_vendor) / 100.0)
    elif not expected_vendor and not actual_vendor:
        scores.append(1.0)
    else:
        scores.append(0.0)

    expected_due = normalize_date(expected.get("due_date"))
    actual_due = normalize_date(actual.get("due_date"))
    if expected_due == actual_due:
        scores.append(1.0)
    elif expected_due is None or actual_due is None:
        scores.append(0.5 if expected_due is None and actual_due is None else 0.0)
    else:
        scores.append(1.0 if expected_due == actual_due else 0.0)

    return round(sum(scores) / len(scores), 4)


def load_baseline() -> dict[str, Any]:
    with BASELINE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_eval_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)


def compare_to_baseline(current: dict[str, float], baseline: dict[str, Any]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for key, value in current.items():
        baseline_value = baseline.get(key)
        if isinstance(baseline_value, (int, float)):
            delta = round(value - float(baseline_value), 4)
            comparisons[key] = {
                "current": value,
                "baseline": baseline_value,
                "delta": delta,
                "passed": value >= float(baseline_value),
            }
    return comparisons


def format_pr_comment(report: dict[str, Any], baseline: dict[str, Any]) -> str:
    lines = [
        "## FinFlow AI Eval Results",
        "",
        "| Metric | Current | Baseline | Status |",
        "|--------|---------|----------|--------|",
    ]
    comparisons = compare_to_baseline(report["metrics"], baseline)
    for key, item in comparisons.items():
        label = key.replace("_", " ").title()
        status = "✅" if item["passed"] else "❌"
        lines.append(
            f"| {label} | {item['current']:.1%} | {item['baseline']:.1%} | {status} |"
        )
    lines.extend(["", f"_Generated at {report.get('generated_at', 'unknown')}_"])
    return "\n".join(lines)
