#!/usr/bin/env python3
"""Merge eval reports and emit a PR comment markdown body."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from evals.helpers.metrics import compare_to_baseline, format_pr_comment, load_baseline

EVALS_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = EVALS_ROOT / "reports"
OUTPUT_PATH = REPORTS_DIR / "pr_comment.md"


def main() -> int:
    baseline = load_baseline()
    merged_metrics: dict[str, float] = {}
    sections: list[str] = []
    generated_at = None

    for report_name in ("extraction_report.json", "reconciliation_report.json"):
        report_path = REPORTS_DIR / report_name
        if not report_path.exists():
            continue
        with report_path.open(encoding="utf-8") as handle:
            report = json.load(handle)
        generated_at = report.get("generated_at", generated_at)
        merged_metrics.update(report.get("metrics", {}))
        sections.append(format_pr_comment(report, baseline))

    if not merged_metrics:
        print("No eval reports found.", file=sys.stderr)
        return 1

    combined = {
        "metrics": merged_metrics,
        "generated_at": generated_at,
    }
    comparisons = compare_to_baseline(merged_metrics, baseline)
    failed = [key for key, item in comparisons.items() if not item["passed"]]

    body_parts = sections or [format_pr_comment(combined, baseline)]
    body = "\n\n".join(body_parts)
    if failed:
        body += "\n\n**Quality gate failed** for: " + ", ".join(failed)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(body, encoding="utf-8")
    print(body)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
