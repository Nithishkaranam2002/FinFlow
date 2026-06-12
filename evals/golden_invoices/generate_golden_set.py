#!/usr/bin/env python3
"""Build the golden invoice evaluation set from synthetic data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_PATH = PROJECT_ROOT / "data" / "synthetic_data.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "golden_invoices.json"

TARGET_COUNT = 50
CATEGORY_QUOTAS = {
    "clean": 20,
    "messy": 15,
    "duplicate": 10,
    "threshold": 5,
}


def _normalize_expected(invoice: dict) -> dict:
    extracted = invoice.get("extracted_data") or {}
    due_date = extracted.get("due_date") or invoice.get("due_date")
    if due_date and not str(due_date).startswith("20"):
        due_date = None
    amount = extracted.get("amount") or invoice.get("amount")
    return {
        "total_amount": str(Decimal(str(amount)).quantize(Decimal("0.01"))),
        "vendor_name": extracted.get("vendor_name") or "",
        "due_date": due_date if due_date else None,
        "invoice_number": invoice.get("invoice_number"),
    }


def _category(invoice: dict) -> str:
    flags = invoice.get("flags") or {}
    if flags.get("threshold_avoidance"):
        return "threshold"
    if flags.get("duplicate_pair"):
        return "duplicate"
    messy_keys = {"missing_due_date", "amount_as_text", "vendor_name_misspelled"}
    if messy_keys.intersection(flags.keys()):
        return "messy"
    return "clean"


def _messy_flags(invoice: dict) -> list[str]:
    flags = invoice.get("flags") or {}
    return sorted(
        key
        for key in ("missing_due_date", "amount_as_text", "vendor_name_misspelled")
        if flags.get(key)
    )


def select_golden_invoices(invoices: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = {key: [] for key in CATEGORY_QUOTAS}
    for invoice in invoices:
        buckets[_category(invoice)].append(invoice)

    selected: list[dict] = []
    for category, quota in CATEGORY_QUOTAS.items():
        selected.extend(buckets[category][:quota])

    if len(selected) < TARGET_COUNT:
        remaining = [inv for inv in invoices if inv not in selected]
        selected.extend(remaining[: TARGET_COUNT - len(selected)])

    golden_rows = []
    for invoice in selected[:TARGET_COUNT]:
        golden_rows.append(
            {
                "id": invoice["id"],
                "tenant_id": invoice["tenant_id"],
                "vendor_id": invoice["vendor_id"],
                "invoice_number": invoice["invoice_number"],
                "category": _category(invoice),
                "messy_flags": _messy_flags(invoice),
                "flags": invoice.get("flags", {}),
                "pdf_text": invoice.get("pdf_text", ""),
                "expected": _normalize_expected(invoice),
            }
        )
    return golden_rows


def build_duplicate_pairs(invoices: list[dict]) -> list[dict]:
    pairs = []
    for invoice in invoices:
        flags = invoice.get("flags") or {}
        if flags.get("duplicate_pair") and flags.get("duplicate_of"):
            pairs.append(
                {
                    "target_invoice_id": invoice["id"],
                    "source_invoice_id": flags["duplicate_of"],
                    "tenant_id": invoice["tenant_id"],
                    "vendor_id": invoice["vendor_id"],
                }
            )
    return pairs


def build_threshold_invoices(invoices: list[dict]) -> list[dict]:
    rows = []
    for invoice in invoices:
        flags = invoice.get("flags") or {}
        if flags.get("threshold_avoidance"):
            rows.append(
                {
                    "invoice_id": invoice["id"],
                    "tenant_id": invoice["tenant_id"],
                    "vendor_id": invoice["vendor_id"],
                    "invoice_number": invoice["invoice_number"],
                    "amount": invoice["amount"],
                    "approval_threshold": flags.get("approval_threshold", "5000.00"),
                }
            )
    return rows


def main() -> None:
    if not SYNTHETIC_PATH.exists():
        raise SystemExit(
            f"Synthetic data not found at {SYNTHETIC_PATH}. "
            "Run: uv run python scripts/generate_synthetic_data.py"
        )

    with SYNTHETIC_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    invoices = payload["invoices"]
    golden_invoices = select_golden_invoices(invoices)
    duplicate_pairs = build_duplicate_pairs(invoices)
    threshold_invoices = build_threshold_invoices(invoices)

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": str(SYNTHETIC_PATH.relative_to(PROJECT_ROOT)),
            "count": len(golden_invoices),
            "category_counts": {
                category: sum(1 for row in golden_invoices if row["category"] == category)
                for category in CATEGORY_QUOTAS
            },
            "duplicate_pair_count": len(duplicate_pairs),
            "threshold_invoice_count": len(threshold_invoices),
        },
        "invoices": golden_invoices,
        "duplicate_pairs": duplicate_pairs,
        "threshold_invoices": threshold_invoices,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)

    print(f"Wrote {len(golden_invoices)} golden invoices to {OUTPUT_PATH}")
    print(f"  Duplicate pairs: {len(duplicate_pairs)}")
    print(f"  Threshold invoices: {len(threshold_invoices)}")


if __name__ == "__main__":
    main()
