#!/usr/bin/env python3
"""Generate realistic, messy synthetic data for FinFlow testing."""

from __future__ import annotations

import json
import random
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from faker import Faker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "synthetic_data.json"
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

TENANT_SPECS = [
    ("Acme Corp", "acme-corp"),
    ("TechNova Ltd", "technova-ltd"),
    ("Meridian Foods", "meridian-foods"),
    ("PeakLogistics", "peaklogistics"),
    ("BlueStar Health", "bluestar-health"),
]

INVOICES_PER_TENANT = 100
VENDORS_PER_TENANT = 20
BANK_LINES_PER_TENANT = 100
APPROVAL_THRESHOLD = Decimal("5000.00")

ERROR_COUNTS = {
    "missing_due_dates": 30,
    "text_amounts": 20,
    "duplicate_invoices": 15,
    "misspelled_vendors": 10,
    "threshold_avoidance": 5,
}


def stable_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{key}"))


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def amount_to_words(amount: Decimal) -> str:
    dollars = int(amount)
    mappings = {
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
        11: "eleven",
        12: "twelve",
        13: "thirteen",
        14: "fourteen",
        15: "fifteen",
        20: "twenty",
        30: "thirty",
        40: "forty",
        50: "fifty",
        60: "sixty",
        70: "seventy",
        80: "eighty",
        90: "ninety",
        100: "one hundred",
        1000: "one thousand",
        2000: "two thousand",
        3000: "three thousand",
        4000: "four thousand",
        5000: "five thousand",
        10000: "ten thousand",
        14000: "fourteen thousand",
        25000: "twenty-five thousand",
    }
    if dollars in mappings:
        return f"{mappings[dollars]} dollars"
    if dollars >= 1000 and dollars % 1000 == 0:
        return f"{dollars // 1000} thousand dollars"
    return f"{dollars:,} dollars"


def misspell_vendor(name: str) -> str:
    variants = {
        "Acme Corp": "Acme Corrp",
        "TechNova Ltd": "Tech Nova LTD",
        "Meridian Foods": "Meridain Foods",
        "PeakLogistics": "Peak Logistic",
        "BlueStar Health": "Blue Star Healt",
    }
    if name in variants:
        return variants[name]
    if " " in name:
        parts = name.split()
        parts[0] = parts[0][:-1] + random.choice("aeiou")
        return " ".join(parts)
    return name[:-2] + "LT" if len(name) > 4 else name + "X"


def garble_vendor_name(name: str) -> str:
    garbled = name.upper()
    garbled = garbled.replace("LIMITED", "LT").replace("LTD", "LT")
    garbled = garbled.replace("CORPORATION", "CORP").replace("INC", "")
    garbled = re.sub(r"\s+", " ", garbled).strip()
    if len(garbled) > 18:
        garbled = garbled[:18]
    return garbled


def duplicate_invoice_number(original: str) -> str:
    normalized = original.replace("-", "").replace(" ", "")
    if "-" in original:
        return normalized
    match = re.search(r"(\d+)$", original)
    if match:
        prefix = original[: match.start()]
        return f"{prefix}{match.group(1)}"
    return normalized


def build_pdf_text(
    *,
    tenant_name: str,
    vendor_name: str,
    invoice_number: str,
    amount: Decimal,
    amount_text: str | None,
    due_date: date | None,
    line_items: list[dict],
) -> str:
    due_line = (
        due_date.isoformat()
        if due_date
        else random.choice(["TBD", "Net 30 from receipt", "Upon receipt", ""])
    )
    amount_line = amount_text or f"${amount:,.2f}"
    lines = [
        f"INVOICE — {vendor_name}",
        f"Bill To: {tenant_name}",
        f"Invoice Number: {invoice_number}",
        f"Invoice Date: {(date.today() - timedelta(days=random.randint(5, 90))).isoformat()}",
        f"Due Date: {due_line}",
        "",
        "Description                          Qty    Unit       Amount",
        "-" * 62,
    ]
    for item in line_items:
        lines.append(
            f"{item['description'][:32]:<32} {item['quantity']:>4} "
            f"{item['unit_price']:>10} {item['total']:>10}"
        )
    lines.extend(
        [
            "-" * 62,
            f"TOTAL DUE: {amount_line}",
            "",
            "Remit payment to the address above. Include invoice number with payment.",
            "Questions? accounts@example.com",
        ]
    )
    return "\n".join(lines)


def generate_line_items(amount: Decimal, faker: Faker) -> list[dict]:
    count = random.randint(1, 4)
    remaining = amount
    items: list[dict] = []
    for idx in range(count):
        if idx == count - 1:
            line_total = remaining
        else:
            line_total = (remaining / (count - idx)).quantize(Decimal("0.01"))
            remaining -= line_total
        qty = random.randint(1, 10)
        unit = (line_total / qty).quantize(Decimal("0.01"))
        items.append(
            {
                "description": faker.bs().title(),
                "quantity": qty,
                "unit_price": str(unit),
                "total": str(line_total),
            }
        )
    return items


def generate_tenants() -> list[dict]:
    tenants = []
    for name, slug in TENANT_SPECS:
        tenants.append(
            {
                "id": stable_id("tenant", slug),
                "name": name,
                "slug": slug,
                "is_active": True,
                "config": {
                    "approval_threshold": str(APPROVAL_THRESHOLD),
                    "payment_terms_default": 30,
                    "policy_rules": {
                        "require_dual_approval_above": "25000.00",
                        "auto_match_confidence": 0.92,
                    },
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return tenants


def generate_vendors(tenants: list[dict], faker: Faker) -> list[dict]:
    vendors: list[dict] = []
    for tenant in tenants:
        for idx in range(VENDORS_PER_TENANT):
            company = faker.company()
            terms = random.choice([30, 30, 30, 60, 60, 45])
            risk = round(random.uniform(0.05, 0.95), 3)
            vendor_id = stable_id("vendor", f"{tenant['slug']}-{idx}")
            email_slug = slugify(company)[:40]
            vendors.append(
                {
                    "id": vendor_id,
                    "tenant_id": tenant["id"],
                    "name": company,
                    "email": f"ap-{email_slug}@{faker.free_email_domain()}",
                    "bank_account": f"****{random.randint(1000, 9999)}",
                    "bank_account_changed_at": None,
                    "payment_terms_days": terms,
                    "total_invoices": 0,
                    "total_paid": "0.00",
                    "risk_score": risk,
                    "is_active": True,
                }
            )
    return vendors


def assign_error_slots(total: int) -> dict[str, list[int]]:
    rng = random.Random(42)
    indices = list(range(total))
    rng.shuffle(indices)
    cursor = 0

    def take(count: int) -> list[int]:
        nonlocal cursor
        selected = indices[cursor : cursor + count]
        cursor += count
        return selected

    duplicate_sources = take(ERROR_COUNTS["duplicate_invoices"])
    duplicate_targets = take(ERROR_COUNTS["duplicate_invoices"])

    return {
        "missing_due_dates": take(ERROR_COUNTS["missing_due_dates"]),
        "text_amounts": take(ERROR_COUNTS["text_amounts"]),
        "duplicate_sources": duplicate_sources,
        "duplicate_targets": duplicate_targets,
        "misspelled_vendors": take(ERROR_COUNTS["misspelled_vendors"]),
        "threshold_avoidance": take(ERROR_COUNTS["threshold_avoidance"]),
    }


def generate_invoices(
    tenants: list[dict],
    vendors: list[dict],
    faker: Faker,
) -> tuple[list[dict], dict[str, int]]:
    vendors_by_tenant: dict[str, list[dict]] = {}
    for vendor in vendors:
        vendors_by_tenant.setdefault(vendor["tenant_id"], []).append(vendor)

    tenant_lookup = {t["id"]: t for t in tenants}
    invoices: list[dict] = []
    global_index = 0
    error_slots = assign_error_slots(len(tenants) * INVOICES_PER_TENANT)
    injected = {key: 0 for key in ERROR_COUNTS}
    injected["duplicate_pairs"] = 0

    for tenant in tenants:
        tenant_vendors = vendors_by_tenant[tenant["id"]]
        for local_idx in range(INVOICES_PER_TENANT):
            vendor = random.choice(tenant_vendors)
            amount = Decimal(str(random.randint(150, 75000)))
            if amount > 1000:
                amount = amount.quantize(Decimal("0.01"))

            invoice_number = f"INV-{date.today().year}-{local_idx + 1:04d}"
            due_date = date.today() + timedelta(days=random.randint(10, 90))
            line_items = generate_line_items(amount, faker)
            flags: dict = {}
            extracted_vendor_name = vendor["name"]
            amount_text: str | None = None
            ambiguous_due = None

            if global_index in error_slots["missing_due_dates"]:
                due_date = None
                ambiguous_due = random.choice(["Net 30", "End of month", "TBD", None])
                flags["missing_due_date"] = True
                injected["missing_due_dates"] += 1

            if global_index in error_slots["text_amounts"]:
                amount_text = amount_to_words(amount)
                flags["amount_as_text"] = True
                injected["text_amounts"] += 1

            if global_index in error_slots["misspelled_vendors"]:
                extracted_vendor_name = misspell_vendor(vendor["name"])
                flags["vendor_name_misspelled"] = True
                injected["misspelled_vendors"] += 1

            if global_index in error_slots["threshold_avoidance"]:
                amount = APPROVAL_THRESHOLD - Decimal(str(random.randint(5, 120)))
                line_items = generate_line_items(amount, faker)
                flags["threshold_avoidance"] = True
                flags["approval_threshold"] = str(APPROVAL_THRESHOLD)
                injected["threshold_avoidance"] += 1

            invoice_id = stable_id("invoice", f"{tenant['slug']}-{local_idx}")
            invoice = {
                "id": invoice_id,
                "tenant_id": tenant["id"],
                "vendor_id": vendor["id"],
                "invoice_number": invoice_number,
                "amount": str(amount),
                "currency": "USD",
                "due_date": due_date.isoformat() if due_date else None,
                "line_items": line_items,
                "status": random.choice(
                    ["received", "extracting", "review_required", "matched", "approved"]
                ),
                "extraction_confidence": round(random.uniform(0.55, 0.99), 3),
                "extracted_data": {
                    "vendor_name": extracted_vendor_name,
                    "invoice_number": invoice_number,
                    "amount": str(amount),
                    "amount_text": amount_text,
                    "due_date": due_date.isoformat() if due_date else ambiguous_due,
                    "currency": "USD",
                    "line_items": line_items,
                    "source_format": random.choice(["pdf", "png", "email_body", "edi"]),
                },
                "flags": flags,
                "pdf_text": build_pdf_text(
                    tenant_name=tenant["name"],
                    vendor_name=extracted_vendor_name,
                    invoice_number=invoice_number,
                    amount=amount,
                    amount_text=amount_text,
                    due_date=due_date,
                    line_items=line_items,
                ),
            }
            invoices.append(invoice)
            global_index += 1

    invoice_by_index = {i: inv for i, inv in enumerate(invoices)}
    for src_idx, tgt_idx in zip(
        error_slots["duplicate_sources"],
        error_slots["duplicate_targets"],
        strict=True,
    ):
        source = invoice_by_index[src_idx]
        target = invoice_by_index[tgt_idx]
        target_vendor = next(v for v in vendors if v["id"] == source["vendor_id"])
        dup_number = duplicate_invoice_number(source["invoice_number"])
        target.update(
            {
                "vendor_id": source["vendor_id"],
                "invoice_number": dup_number,
                "amount": source["amount"],
                "line_items": source["line_items"],
                "flags": {
                    **target.get("flags", {}),
                    "duplicate_of": source["id"],
                    "duplicate_pair": True,
                },
                "extracted_data": {
                    **source["extracted_data"],
                    "invoice_number": dup_number,
                    "duplicate_of": source["id"],
                },
                "pdf_text": build_pdf_text(
                    tenant_name=tenant_lookup[source["tenant_id"]]["name"],
                    vendor_name=target_vendor["name"],
                    invoice_number=dup_number,
                    amount=Decimal(source["amount"]),
                    amount_text=source["extracted_data"].get("amount_text"),
                    due_date=(
                        date.fromisoformat(source["due_date"])
                        if source.get("due_date")
                        else None
                    ),
                    line_items=source["line_items"],
                ),
            }
        )
        injected["duplicate_invoices"] += 1
        injected["duplicate_pairs"] += 1

    return invoices, injected


def generate_bank_lines(
    tenants: list[dict],
    vendors: list[dict],
    invoices: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    vendors_by_tenant: dict[str, list[dict]] = {}
    for vendor in vendors:
        vendors_by_tenant.setdefault(vendor["tenant_id"], []).append(vendor)

    invoices_by_tenant: dict[str, list[dict]] = {}
    for invoice in invoices:
        invoices_by_tenant.setdefault(invoice["tenant_id"], []).append(invoice)

    bank_lines: list[dict] = []
    stats = {
        "truncated_references": 0,
        "garbled_vendor_names": 0,
        "bundled_payments": 0,
        "timing_differences": 0,
        "non_ascii_descriptions": 0,
        "wire_transfer_only": 0,
    }

    non_ascii_snippets = [
        "PAYMT — ACME “SERVICES”",
        "INV–2024–001 • wire",
        "TRANSFERREF 8842",
        "PAYMENT – vendor\u2019s invoice",
    ]

    line_counter = 0
    for tenant in tenants:
        tenant_invoices = invoices_by_tenant[tenant["id"]]
        rng = random.Random(tenant["slug"])
        bundled_pool = set()

        for local_idx in range(BANK_LINES_PER_TENANT):
            line_id = stable_id("bank_line", f"{tenant['slug']}-{local_idx}")
            issues: list[str] = []
            linked_invoice_ids: list[str] = []

            if local_idx < 10:
                description = "WIRE TRANSFER"
                reference = ""
                amount = Decimal(str(rng.randint(500, 25000)))
                transaction_date = date.today() - timedelta(days=rng.randint(1, 120))
                posted_date = transaction_date
                issues.append("wire_transfer_only")
                stats["wire_transfer_only"] += 1
            else:
                if rng.random() < 0.12 and len(tenant_invoices) >= 2:
                    bundle_size = rng.choice([2, 3])
                    bundle = rng.sample(tenant_invoices, bundle_size)
                    linked_invoice_ids = [inv["id"] for inv in bundle]
                    amount = sum(Decimal(inv["amount"]) for inv in bundle)
                    anchor = bundle[0]
                    vendor = next(v for v in vendors if v["id"] == anchor["vendor_id"])
                    full_ref = anchor["invoice_number"]
                    reference = full_ref[:14] if rng.random() < 0.6 else full_ref
                    if len(reference) < len(full_ref):
                        issues.append("truncated_reference")
                        stats["truncated_references"] += 1
                    description = garble_vendor_name(vendor["name"])
                    issues.extend(["bundled_payment", "garbled_vendor_name"])
                    stats["bundled_payments"] += 1
                    stats["garbled_vendor_names"] += 1
                    bundled_pool.update(linked_invoice_ids)
                else:
                    anchor = rng.choice(tenant_invoices)
                    linked_invoice_ids = [anchor["id"]]
                    amount = Decimal(anchor["amount"])
                    vendor = next(v for v in vendors if v["id"] == anchor["vendor_id"])
                    full_ref = f"PAYMT REF {anchor['invoice_number']}"
                    if rng.random() < 0.35:
                        reference = full_ref[:16]
                        issues.append("truncated_reference")
                        stats["truncated_references"] += 1
                    else:
                        reference = full_ref
                    if rng.random() < 0.4:
                        description = garble_vendor_name(vendor["name"])
                        issues.append("garbled_vendor_name")
                        stats["garbled_vendor_names"] += 1
                    else:
                        description = vendor["name"].upper()

                transaction_date = date.today() - timedelta(days=rng.randint(1, 120))
                posted_date = transaction_date
                if rng.random() < 0.15:
                    if transaction_date.day >= 28:
                        posted_date = transaction_date + timedelta(days=1)
                        issues.append("timing_difference")
                        stats["timing_differences"] += 1

                if rng.random() < 0.2:
                    description = rng.choice(non_ascii_snippets) + f" {description}"
                    issues.append("non_ascii_description")
                    stats["non_ascii_descriptions"] += 1

            bank_lines.append(
                {
                    "id": line_id,
                    "tenant_id": tenant["id"],
                    "transaction_date": transaction_date.isoformat(),
                    "posted_date": posted_date.isoformat(),
                    "amount": str(-amount),
                    "description": description,
                    "reference": reference,
                    "linked_invoice_ids": linked_invoice_ids,
                    "data_quality_issues": issues,
                }
            )
            line_counter += 1

    return bank_lines, stats


def estimate_match_rate(bank_lines: list[dict]) -> dict:
    total = len(bank_lines)
    exact = 0
    fuzzy = 0
    hard = 0
    for line in bank_lines:
        issues = set(line["data_quality_issues"])
        if "wire_transfer_only" in issues:
            hard += 1
        elif "bundled_payment" in issues:
            fuzzy += 1
        elif "truncated_reference" in issues or "garbled_vendor_name" in issues:
            fuzzy += 1
        elif "timing_difference" in issues or "non_ascii_description" in issues:
            fuzzy += 1
        else:
            exact += 1

    exact_rate = exact / total
    fuzzy_rate = fuzzy / total
    hard_rate = hard / total
    expected_good_system = exact_rate + fuzzy_rate * 0.75

    return {
        "total_bank_lines": total,
        "exact_matchable_pct": round(exact_rate * 100, 1),
        "fuzzy_matchable_pct": round(fuzzy_rate * 100, 1),
        "hard_unmatchable_pct": round(hard_rate * 100, 1),
        "expected_match_rate_good_system_pct": round(expected_good_system * 100, 1),
        "expected_match_rate_excellent_system_pct": round(
            (exact_rate + fuzzy_rate * 0.88) * 100, 1
        ),
    }


def main() -> None:
    faker = Faker()
    Faker.seed(42)
    random.seed(42)

    tenants = generate_tenants()
    vendors = generate_vendors(tenants, faker)
    invoices, invoice_errors = generate_invoices(tenants, vendors, faker)
    bank_lines, bank_errors = generate_bank_lines(tenants, vendors, invoices)
    match_rate = estimate_match_rate(bank_lines)

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed": 42,
            "counts": {
                "tenants": len(tenants),
                "vendors": len(vendors),
                "invoices": len(invoices),
                "bank_statement_lines": len(bank_lines),
            },
            "intentional_invoice_errors": invoice_errors,
            "intentional_bank_line_issues": bank_errors,
            "expected_reconciliation": match_rate,
        },
        "tenants": tenants,
        "vendors": vendors,
        "invoices": invoices,
        "bank_statement_lines": bank_lines,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("FinFlow Synthetic Data Generated")
    print("=" * 60)
    print(f"Output: {OUTPUT_PATH}")
    print()
    print("Entity counts:")
    print(f"  Tenants:              {len(tenants)}")
    print(f"  Vendors:              {len(vendors)}")
    print(f"  Invoices:             {len(invoices)}")
    print(f"  Bank statement lines: {len(bank_lines)}")
    print()
    print("Intentional invoice errors injected:")
    for key, value in invoice_errors.items():
        print(f"  {key}: {value}")
    print()
    print("Bank line data quality issues:")
    for key, value in bank_errors.items():
        print(f"  {key}: {value}")
    print()
    print("Expected reconciliation performance:")
    print(
        f"  Exact-matchable lines:     {match_rate['exact_matchable_pct']}%"
    )
    print(
        f"  Fuzzy-matchable lines:     {match_rate['fuzzy_matchable_pct']}%"
    )
    print(
        f"  Hard/unmatchable lines:    {match_rate['hard_unmatchable_pct']}%"
    )
    print(
        "  Expected match rate (good system):     "
        f"{match_rate['expected_match_rate_good_system_pct']}%"
    )
    print(
        "  Expected match rate (excellent system): "
        f"{match_rate['expected_match_rate_excellent_system_pct']}%"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
