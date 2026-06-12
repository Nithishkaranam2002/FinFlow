"""Database fixtures for reconciliation evaluation runs."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select

from core.database import async_session_factory
from core.tenant import set_current_tenant_id
from models.invoice import Invoice, InvoiceStatus
from models.payment import Payment, PaymentStatus
from models.reconciliation import BankStatement, BankStatementLine, MatchType, ReconciliationMatch, StatementStatus
from models.tenant import Tenant
from models.vendor import Vendor


async def clear_eval_reconciliation_data(tenant_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            delete(ReconciliationMatch).where(ReconciliationMatch.tenant_id == tenant_id)
        )
        await session.execute(
            delete(BankStatementLine).where(BankStatementLine.tenant_id == tenant_id)
        )
        await session.execute(delete(BankStatement).where(BankStatement.tenant_id == tenant_id))
        await session.execute(delete(Payment).where(Payment.tenant_id == tenant_id))
        await session.commit()


async def ensure_invoice_exists(session, invoice_row: dict[str, Any]) -> Invoice:
    invoice_id = uuid.UUID(invoice_row["id"])
    existing = await session.get(Invoice, invoice_id)
    if existing:
        return existing

    session.add(
        Invoice(
            id=invoice_id,
            tenant_id=uuid.UUID(invoice_row["tenant_id"]),
            vendor_id=uuid.UUID(invoice_row["vendor_id"]),
            invoice_number=invoice_row["invoice_number"],
            amount=Decimal(str(invoice_row["amount"])),
            currency=invoice_row.get("currency", "USD"),
            due_date=(
                datetime.fromisoformat(invoice_row["due_date"]).date()
                if invoice_row.get("due_date")
                else None
            ),
            line_items=invoice_row.get("line_items", []),
            status=InvoiceStatus.APPROVED,
            extraction_confidence=invoice_row.get("extraction_confidence"),
            extracted_data=invoice_row.get("extracted_data"),
            flags=invoice_row.get("flags", {}),
        )
    )
    await session.flush()
    return await session.get(Invoice, invoice_id)


async def setup_reconciliation_eval_dataset(
    golden: dict[str, Any],
    synthetic_invoices: list[dict[str, Any]],
) -> tuple[str, str]:
    tenant_id = uuid.UUID(golden["tenant_id"])
    statement_id = uuid.uuid4()

    invoice_lookup = {row["id"]: row for row in synthetic_invoices}
    await clear_eval_reconciliation_data(tenant_id)

    async with async_session_factory() as session:
        set_current_tenant_id(tenant_id)
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise RuntimeError(f"Tenant {tenant_id} not found. Seed synthetic data first.")

        statement = BankStatement(
            id=statement_id,
            tenant_id=tenant_id,
            filename="eval-golden-statement.csv",
            source_format="csv",
            status=StatementStatus.PROCESSING,
            line_count=len(golden["pairs"]),
        )
        session.add(statement)
        await session.flush()

        for pair in golden["pairs"]:
            invoice_row = invoice_lookup.get(pair["invoice_id"])
            if not invoice_row:
                raise RuntimeError(f"Invoice {pair['invoice_id']} missing from synthetic data")

            invoice = await ensure_invoice_exists(session, invoice_row)
            vendor = await session.get(Vendor, invoice.vendor_id)
            txn_date = datetime.fromisoformat(pair["bank_line"]["transaction_date"]).date()
            amount = abs(Decimal(str(pair["bank_line"]["amount"])))

            payment_reference = pair["bank_line"].get("reference") or ""
            if pair.get("payment_reference_full"):
                payment_reference = pair["payment_reference_full"]
            elif not payment_reference:
                payment_reference = f"PAYMT REF {invoice.invoice_number}"

            payment = Payment(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                amount=amount,
                status=PaymentStatus.CLEARED,
                payment_reference=payment_reference,
                bank_transaction_id=pair["bank_line"].get("reference") or invoice.invoice_number,
                cleared_at=datetime.combine(txn_date, time.min, tzinfo=timezone.utc),
            )
            session.add(payment)

            line = BankStatementLine(
                id=uuid.UUID(pair["bank_line"]["id"]) if pair["bank_line"].get("id") else uuid.uuid4(),
                tenant_id=tenant_id,
                statement_id=statement_id,
                transaction_date=txn_date,
                description=pair["bank_line"]["description"],
                amount=-amount,
                reference=pair["bank_line"].get("reference"),
                bank_transaction_id=pair["bank_line"].get("reference"),
                currency=pair["bank_line"].get("currency", "USD"),
                is_matched=False,
            )
            session.add(line)

        await session.commit()

    return str(statement_id), str(tenant_id)


async def collect_reconciliation_results(statement_id: str, tenant_id: str) -> dict[str, Any]:
    async with async_session_factory() as session:
        set_current_tenant_id(uuid.UUID(tenant_id))
        lines_result = await session.execute(
            select(BankStatementLine).where(
                BankStatementLine.statement_id == uuid.UUID(statement_id),
                BankStatementLine.tenant_id == uuid.UUID(tenant_id),
            )
        )
        lines = list(lines_result.scalars().all())

        matches_result = await session.execute(
            select(ReconciliationMatch).where(
                ReconciliationMatch.statement_id == uuid.UUID(statement_id),
                ReconciliationMatch.tenant_id == uuid.UUID(tenant_id),
            )
        )
        matches = list(matches_result.scalars().all())

    total = len(lines)
    matched = sum(1 for line in lines if line.is_matched)
    exact = sum(1 for match in matches if match.match_type == MatchType.EXACT)
    fuzzy = sum(1 for match in matches if match.match_type == MatchType.FUZZY)
    llm = sum(1 for match in matches if match.match_type == MatchType.LLM_JUDGMENT)

    unmatched_lines = [line for line in lines if not line.is_matched]
    return {
        "total_lines": total,
        "matched_lines": matched,
        "match_rate": matched / total if total else 0.0,
        "exact_fuzzy_rate": (exact + fuzzy) / total if total else 0.0,
        "exact_matched": exact,
        "fuzzy_matched": fuzzy,
        "llm_matched": llm,
        "unmatched_lines": unmatched_lines,
        "matches": matches,
    }
