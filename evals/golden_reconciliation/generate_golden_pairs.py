#!/usr/bin/env python3
"""Build golden bank-line-to-invoice reconciliation pairs from synthetic data."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_PATH = PROJECT_ROOT / "data" / "synthetic_data.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "golden_reconciliation.json"

TARGET_PAIRS = 30
PRIORITY_ISSUES = (
    "truncated_reference",
    "garbled_vendor_name",
    "bundled_payment",
    "non_ascii_description",
    "timing_difference",
)


def _score_line(line: dict) -> tuple[int, int]:
    issues = set(line.get("data_quality_issues") or [])
    if "wire_transfer_only" in issues:
        return (-1, 0)
    if not line.get("linked_invoice_ids"):
        return (-1, 0)
    priority_hits = sum(1 for issue in PRIORITY_ISSUES if issue in issues)
    return (priority_hits, len(line.get("linked_invoice_ids", [])))


def select_pairs(bank_lines: list[dict], invoices: list[dict]) -> list[dict]:
    invoice_lookup = {row["id"]: row for row in invoices}
    ranked = sorted(
        (line for line in bank_lines if line.get("linked_invoice_ids")),
        key=_score_line,
        reverse=True,
    )

    pairs: list[dict] = []
    used_line_ids: set[str] = set()

    def add_pair(line: dict) -> None:
        if line["id"] in used_line_ids:
            return
        invoice_id = line["linked_invoice_ids"][0]
        invoice = invoice_lookup.get(invoice_id)
        if not invoice:
            return
        payment_reference_full = f"PAYMT REF {invoice['invoice_number']}"
        pairs.append(
            {
                "pair_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"golden-recon-{line['id']}")),
                "tenant_id": line["tenant_id"],
                "invoice_id": invoice_id,
                "expected_invoice_ids": line["linked_invoice_ids"],
                "expected_match_types": ["exact", "fuzzy"],
                "data_quality_issues": line.get("data_quality_issues", []),
                "payment_reference_full": payment_reference_full,
                "bank_line": {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"eval-line-{line['id']}")),
                    "transaction_date": line["transaction_date"],
                    "amount": line["amount"],
                    "description": line["description"],
                    "reference": line.get("reference"),
                    "currency": "USD",
                },
            }
        )
        used_line_ids.add(line["id"])

    messy_target = max(12, TARGET_PAIRS // 2)
    messy_count = 0
    for line in ranked:
        issues = set(line.get("data_quality_issues") or [])
        if issues.intersection(PRIORITY_ISSUES) and messy_count < messy_target:
            add_pair(line)
            messy_count += 1
        if len(pairs) >= TARGET_PAIRS:
            break

    for line in ranked:
        if len(pairs) >= TARGET_PAIRS:
            break
        add_pair(line)

    return pairs[:TARGET_PAIRS]


def main() -> None:
    if not SYNTHETIC_PATH.exists():
        raise SystemExit(
            f"Synthetic data not found at {SYNTHETIC_PATH}. "
            "Run: uv run python scripts/generate_synthetic_data.py"
        )

    with SYNTHETIC_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    pairs = select_pairs(payload["bank_statement_lines"], payload["invoices"])
    tenant_id = pairs[0]["tenant_id"] if pairs else payload["tenants"][0]["id"]

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": str(SYNTHETIC_PATH.relative_to(PROJECT_ROOT)),
            "pair_count": len(pairs),
            "tenant_id": tenant_id,
            "messy_pair_count": sum(
                1
                for pair in pairs
                if set(pair.get("data_quality_issues", [])).intersection(PRIORITY_ISSUES)
            ),
        },
        "tenant_id": tenant_id,
        "pairs": pairs,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)

    print(f"Wrote {len(pairs)} golden reconciliation pairs to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
