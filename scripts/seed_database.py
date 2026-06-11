#!/usr/bin/env python3
"""Seed PostgreSQL from data/synthetic_data.json."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_factory
from models.invoice import Invoice, InvoiceStatus
from models.payment import Payment
from models.reconciliation import MatchType, ReconciliationMatch
from models.tenant import Tenant
from models.user import User
from models.vendor import Vendor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "synthetic_data.json"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


async def clear_tenant_scoped_data(
    session: AsyncSession, tenant_ids: list[uuid.UUID]
) -> None:
    await session.execute(
        delete(ReconciliationMatch).where(ReconciliationMatch.tenant_id.in_(tenant_ids))
    )
    await session.execute(delete(Payment).where(Payment.tenant_id.in_(tenant_ids)))
    await session.execute(delete(Invoice).where(Invoice.tenant_id.in_(tenant_ids)))
    await session.execute(delete(Vendor).where(Vendor.tenant_id.in_(tenant_ids)))
    await session.execute(delete(User).where(User.tenant_id.in_(tenant_ids)))
    await session.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    await session.commit()


async def seed_database(data_path: Path, reset: bool) -> dict[str, int]:
    with data_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    counts = {"tenants": 0, "vendors": 0, "invoices": 0, "reconciliation_matches": 0}

    tenant_ids = [uuid.UUID(t["id"]) for t in payload["tenants"]]

    async with async_session_factory() as session:
        if reset:
            await clear_tenant_scoped_data(session, tenant_ids)

        existing = await session.execute(
            select(Tenant.id).where(Tenant.id.in_(tenant_ids))
        )
        if existing.first() and not reset:
            raise RuntimeError(
                "Synthetic tenants already exist. Re-run with --reset to replace data."
            )

        for row in payload["tenants"]:
            session.add(
                Tenant(
                    id=uuid.UUID(row["id"]),
                    name=row["name"],
                    slug=row["slug"],
                    is_active=row["is_active"],
                    config=row.get("config", {}),
                    created_at=parse_datetime(row.get("created_at"))
                    or datetime.now(timezone.utc),
                )
            )
            counts["tenants"] += 1

        for row in payload["vendors"]:
            session.add(
                Vendor(
                    id=uuid.UUID(row["id"]),
                    tenant_id=uuid.UUID(row["tenant_id"]),
                    name=row["name"],
                    email=row.get("email"),
                    bank_account=row.get("bank_account"),
                    bank_account_changed_at=parse_datetime(
                        row.get("bank_account_changed_at")
                    ),
                    payment_terms_days=row.get("payment_terms_days", 30),
                    total_invoices=row.get("total_invoices", 0),
                    total_paid=Decimal(row.get("total_paid", "0.00")),
                    risk_score=row.get("risk_score", 0.0),
                    is_active=row.get("is_active", True),
                )
            )
            counts["vendors"] += 1

        await session.flush()

        vendor_invoice_counts: dict[uuid.UUID, int] = {}
        vendor_paid_totals: dict[uuid.UUID, Decimal] = {}

        for row in payload["invoices"]:
            vendor_id = uuid.UUID(row["vendor_id"])
            tenant_id = uuid.UUID(row["tenant_id"])
            amount = Decimal(row["amount"])
            vendor_invoice_counts[vendor_id] = vendor_invoice_counts.get(vendor_id, 0) + 1
            if row.get("status") in {"approved", "paid", "matched"}:
                vendor_paid_totals[vendor_id] = (
                    vendor_paid_totals.get(vendor_id, Decimal("0.00")) + amount
                )

            extracted = row.get("extracted_data") or {}
            if row.get("pdf_text"):
                extracted = {**extracted, "pdf_text": row["pdf_text"]}

            session.add(
                Invoice(
                    id=uuid.UUID(row["id"]),
                    tenant_id=tenant_id,
                    vendor_id=vendor_id,
                    invoice_number=row["invoice_number"],
                    amount=amount,
                    currency=row.get("currency", "USD"),
                    due_date=parse_date(row.get("due_date")),
                    line_items=row.get("line_items", []),
                    status=InvoiceStatus(row.get("status", "received")),
                    extraction_confidence=row.get("extraction_confidence"),
                    extracted_data=extracted,
                    flags=row.get("flags", {}),
                )
            )
            counts["invoices"] += 1

        await session.flush()

        for vendor_id, invoice_count in vendor_invoice_counts.items():
            vendor = await session.get(Vendor, vendor_id)
            if vendor:
                vendor.total_invoices = invoice_count
                vendor.total_paid = vendor_paid_totals.get(vendor_id, Decimal("0.00"))

        for row in payload["bank_statement_lines"]:
            linked_ids = [uuid.UUID(value) for value in row.get("linked_invoice_ids", [])]
            primary_invoice_id = linked_ids[0] if len(linked_ids) == 1 else None
            issues = row.get("data_quality_issues", [])

            if "wire_transfer_only" in issues:
                match_type = MatchType.UNMATCHED
                confidence = 0.0
            elif len(linked_ids) > 1:
                match_type = MatchType.FUZZY
                confidence = 0.55
            elif primary_invoice_id:
                match_type = MatchType.EXACT if not issues else MatchType.FUZZY
                confidence = 0.95 if match_type == MatchType.EXACT else 0.72
            else:
                match_type = MatchType.UNMATCHED
                confidence = 0.0

            session.add(
                ReconciliationMatch(
                    id=uuid.UUID(row["id"]),
                    tenant_id=uuid.UUID(row["tenant_id"]),
                    bank_line_id=row["id"],
                    invoice_id=primary_invoice_id,
                    payment_id=None,
                    match_type=match_type,
                    confidence_score=confidence,
                    llm_reasoning=json.dumps(
                        {
                            "description": row.get("description"),
                            "reference": row.get("reference"),
                            "linked_invoice_ids": row.get("linked_invoice_ids", []),
                            "data_quality_issues": issues,
                            "transaction_date": row.get("transaction_date"),
                            "posted_date": row.get("posted_date"),
                            "amount": row.get("amount"),
                        }
                    ),
                    matched_by="seed_database",
                    matched_at=parse_datetime(row.get("posted_date")),
                )
            )
            counts["reconciliation_matches"] += 1

        await session.commit()

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FinFlow database from synthetic JSON")
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_PATH,
        help="Path to synthetic_data.json",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing tenant-scoped data before seeding",
    )
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(
            f"Data file not found: {args.data}\n"
            "Run: uv run python scripts/generate_synthetic_data.py"
        )

    counts = asyncio.run(seed_database(args.data, reset=args.reset))

    print("=" * 60)
    print("FinFlow Database Seeded")
    print("=" * 60)
    for entity, count in counts.items():
        print(f"  {entity}: {count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
