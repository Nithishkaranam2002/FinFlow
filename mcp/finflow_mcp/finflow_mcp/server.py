"""FinFlow MCP server: read-only invoice questions for Claude Desktop (stdio transport).

There are deliberately no write tools. Approving, rejecting or correcting invoices stays
with people in the FinFlow app.
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from finflow_mcp.client import FinFlowClient
from finflow_mcp.reasons import (
    OPEN_STATUSES,
    ROLE_LABELS,
    STATUS_LABELS,
    attention_reasons,
    fraud_flag_label,
    fraud_flags,
    has_fraud_signal,
)

# stdio transport: stdout carries the protocol, so logs go to stderr only.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)
ATTENTION_LIMIT = 25
HISTORY_LIMIT = 15
LINE_ITEM_LIMIT = 20

HISTORY_ACTION_LABELS = {
    "uploaded": "Uploaded",
    "approval_approved": "Approved",
    "approval_rejected": "Rejected",
    "auto_approved": "Auto-approved",
    "extraction_corrected": "Extraction corrected",
    "field_corrected": "Field corrected",
    "fraud_flag_raised": "Fraud flag raised",
}

server = MCPServer(
    name="finflow",
    instructions=(
        "Read-only access to FinFlow accounts-payable data for one company. Use these tools to "
        "answer questions about invoices, approvals and vendor spend. You cannot approve, reject "
        "or change anything: tell the user to do that in the FinFlow app."
    ),
)
client = FinFlowClient()


class PendingInvoice(BaseModel):
    invoice_number: str
    vendor: str
    total: str
    currency: str
    needs_approval_from: str
    waiting_since: str | None
    attention_reasons: list[str]


class PendingApprovals(BaseModel):
    count: int
    invoices: list[PendingInvoice]


class FraudFlagOut(BaseModel):
    flag: str
    severity: str
    detail: str


class LineItemOut(BaseModel):
    description: str
    quantity: str | None
    unit_price: str | None
    amount: str | None


class HistoryEntry(BaseModel):
    when: str
    action: str
    by_role: str
    note: str | None


class InvoiceDetails(BaseModel):
    invoice_number: str
    vendor: str
    status: str
    total: str
    currency: str
    invoice_date: str | None
    due_date: str | None
    extraction_confidence: float | None
    needs_approval_from: str | None
    attention_reasons: list[str]
    fraud_flags: list[FraudFlagOut]
    line_items: list[LineItemOut]
    approval_history: list[HistoryEntry]


class AttentionInvoice(BaseModel):
    invoice_number: str
    vendor: str
    status: str
    total: str
    fraud_flagged: bool
    reasons: list[str]


class InvoicesNeedingAttention(BaseModel):
    total: int
    showing: int
    invoices: list[AttentionInvoice]


class VendorSpend(BaseModel):
    vendor: str
    invoice_count: int
    total: str


class SpendByVendor(BaseModel):
    days: int
    since: str
    currency: str
    grand_total: str
    invoice_count: int
    vendors: list[VendorSpend]


def _vendor(invoice: dict[str, Any], names: dict[str, str]) -> str:
    return names.get(invoice["vendor_id"]) or (invoice.get("extracted_data") or {}).get("vendor_name") or "Unknown vendor"


def _approver(invoice: dict[str, Any]) -> str | None:
    """Role that still has to approve; None once the invoice is decided."""
    role = (invoice.get("flags") or {}).get("required_role")
    if not role or invoice.get("status") not in OPEN_STATUSES:
        return None
    return ROLE_LABELS.get(role, role)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@server.tool(
    title="List invoices waiting for approval",
    description=(
        "List invoices that are waiting for a human approval decision, with vendor, total, "
        "which role must approve (approver or controller) and plain-English reasons to look closer."
    ),
    annotations=READ_ONLY,
)
async def list_pending_approvals() -> PendingApprovals:
    names = await client.vendor_names()
    invoices = await client.list_invoices(status="pending_approval")
    return PendingApprovals(
        count=len(invoices),
        invoices=[
            PendingInvoice(
                invoice_number=invoice["invoice_number"],
                vendor=_vendor(invoice, names),
                total=invoice["amount"],
                currency=invoice["currency"],
                needs_approval_from=_approver(invoice) or "Approver",
                waiting_since=(invoice.get("flags") or {}).get("pending_since"),
                attention_reasons=attention_reasons(invoice),
            )
            for invoice in invoices
        ],
    )


@server.tool(
    title="Get one invoice",
    description=(
        "Look up a single invoice by its invoice number (for example KRES-240518) and return its "
        "status, amounts, dates, fraud flags, attention reasons, line items and approval history."
    ),
    annotations=READ_ONLY,
)
async def get_invoice(invoice_number: str) -> InvoiceDetails:
    matches = await client.get("/invoices/", {"invoice_number": invoice_number, "page_size": 5})
    if not matches["items"]:
        raise ToolError(f"No invoice with number {invoice_number!r} was found.")
    invoice = await client.get(f"/invoices/{matches['items'][0]['id']}")
    audit = await client.get(f"/invoices/{invoice['id']}/audit-trail")
    names = await client.vendor_names()
    extracted = invoice.get("extracted_data") or {}

    history = [
        HistoryEntry(
            when=entry["created_at"],
            action=HISTORY_ACTION_LABELS.get(entry["action"], entry["action"].replace("_", " ").capitalize()),
            by_role=ROLE_LABELS.get(entry["actor_role"], entry["actor_role"]),
            note=entry.get("reason"),
        )
        for entry in reversed(audit[:HISTORY_LIMIT])
    ]

    return InvoiceDetails(
        invoice_number=invoice["invoice_number"],
        vendor=_vendor(invoice, names),
        status=STATUS_LABELS.get(invoice["status"], invoice["status"]),
        total=invoice["amount"],
        currency=invoice["currency"],
        invoice_date=extracted.get("invoice_date"),
        due_date=invoice.get("due_date"),
        extraction_confidence=invoice.get("extraction_confidence"),
        needs_approval_from=_approver(invoice),
        attention_reasons=attention_reasons(invoice),
        fraud_flags=[
            FraudFlagOut(
                flag=fraud_flag_label(flag.get("type", "")),
                severity=flag.get("severity", ""),
                detail=flag.get("description", ""),
            )
            for flag in fraud_flags(invoice)
        ],
        line_items=[
            LineItemOut(
                description=str(line.get("description", "")),
                quantity=None if line.get("quantity") is None else str(line["quantity"]),
                unit_price=None if line.get("unit_price") is None else str(line["unit_price"]),
                amount=None if line.get("total") is None else str(line["total"]),
            )
            for line in (invoice.get("line_items") or [])[:LINE_ITEM_LIMIT]
        ],
        approval_history=history,
    )


@server.tool(
    title="Invoices needing attention",
    description=(
        "List open invoices that need a human look: everything in Review Required plus open "
        "invoices with fraud signals (duplicates, amounts just under approval limits, etc.), "
        "each with plain-English reasons. Fraud-flagged invoices come first, then by amount."
    ),
    annotations=READ_ONLY,
)
async def invoices_needing_attention(limit: int = ATTENTION_LIMIT) -> InvoicesNeedingAttention:
    limit = max(1, min(limit, 100))
    names = await client.vendor_names()
    candidates: list[dict[str, Any]] = []
    for status in ("review_required", "pending_approval", "matched"):
        candidates.extend(await client.list_invoices(status=status))

    flagged = [
        invoice
        for invoice in candidates
        if invoice["status"] == "review_required" or has_fraud_signal(invoice)
    ]
    flagged.sort(key=lambda inv: (not has_fraud_signal(inv), -Decimal(inv["amount"])))

    return InvoicesNeedingAttention(
        total=len(flagged),
        showing=min(limit, len(flagged)),
        invoices=[
            AttentionInvoice(
                invoice_number=invoice["invoice_number"],
                vendor=_vendor(invoice, names),
                status=STATUS_LABELS.get(invoice["status"], invoice["status"]),
                total=invoice["amount"],
                fraud_flagged=has_fraud_signal(invoice),
                reasons=attention_reasons(invoice),
            )
            for invoice in flagged[:limit]
        ],
    )


@server.tool(
    title="Spend by vendor",
    description=(
        "Total spend per vendor over the last N days, from invoices that were approved "
        "(including ones already paid). Uses the approval date when FinFlow recorded one, "
        "otherwise the date the invoice was received. Sorted by total, highest first."
    ),
    annotations=READ_ONLY,
)
async def spend_by_vendor(days: int = 30) -> SpendByVendor:
    days = max(1, min(days, 3650))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    names = await client.vendor_names()
    invoices = await client.list_invoices(status="approved") + await client.list_invoices(status="paid")

    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    for invoice in invoices:
        approved_at = _parse_time((invoice.get("flags") or {}).get("approval_decision_at")) or _parse_time(
            invoice.get("created_at")
        )
        if approved_at is None or approved_at < since:
            continue
        vendor = _vendor(invoice, names)
        totals[vendor] += Decimal(invoice["amount"])
        counts[vendor] += 1

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return SpendByVendor(
        days=days,
        since=since.date().isoformat(),
        currency="USD",
        grand_total=str(sum(totals.values(), Decimal("0.00"))),
        invoice_count=sum(counts.values()),
        vendors=[
            VendorSpend(vendor=vendor, invoice_count=counts[vendor], total=str(total))
            for vendor, total in ranked
        ],
    )


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
