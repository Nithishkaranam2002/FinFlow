"""Notification delivery for approval workflows."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog

from core.config import get_settings

logger = structlog.get_logger(__name__)

SEVERITY_COLORS = {
    "CRITICAL": "#DC2626",
    "HIGH": "#EA580C",
    "MEDIUM": "#CA8A04",
    "LOW": "#2563EB",
}


def build_approval_payload(
    *,
    invoice_id: str,
    tenant_id: str,
    extracted_data: dict[str, Any],
    fraud_flags: list[dict[str, Any]],
    extraction_confidence: float | None,
    required_role: str,
    vendor_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")
    line_items = extracted_data.get("line_items") or []
    line_summary = ", ".join(
        item.get("description", "Item") for item in line_items[:3]
    ) or "No line items extracted"

    deadline = datetime.now(timezone.utc) + timedelta(hours=48)
    return {
        "invoice_id": invoice_id,
        "tenant_id": tenant_id,
        "vendor_name": (vendor_match or {}).get("matched_name")
        or extracted_data.get("vendor_name", "Unknown"),
        "amount": extracted_data.get("total_amount"),
        "currency": extracted_data.get("currency", "USD"),
        "due_date": extracted_data.get("due_date"),
        "invoice_number": extracted_data.get("invoice_number"),
        "line_items_summary": line_summary,
        "fraud_flags": fraud_flags,
        "extraction_confidence": extraction_confidence,
        "required_role": required_role,
        "escalation_deadline": deadline.isoformat(),
        "approve_url": f"{base_url}/api/v1/invoices/{invoice_id}/approve",
        "reject_url": f"{base_url}/api/v1/invoices/{invoice_id}/reject",
    }


async def send_approval_email(recipient: str, payload: dict[str, Any]) -> str | None:
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("resend_not_configured", recipient=recipient)
        return None

    flags_html = "".join(
        (
            f"<li style='color:{SEVERITY_COLORS.get(flag.get('severity','LOW'), '#111827')}'>"
            f"<strong>{flag.get('type')}</strong> ({flag.get('severity')}): "
            f"{flag.get('description')}</li>"
        )
        for flag in payload.get("fraud_flags", [])
    ) or "<li>No fraud flags</li>"

    html = f"""
    <h2>Invoice Approval Required</h2>
    <p><strong>Vendor:</strong> {payload.get('vendor_name')}</p>
    <p><strong>Amount:</strong> {payload.get('currency')} {payload.get('amount')}</p>
    <p><strong>Due Date:</strong> {payload.get('due_date') or 'N/A'}</p>
    <p><strong>Invoice #:</strong> {payload.get('invoice_number')}</p>
    <p><strong>Line Items:</strong> {payload.get('line_items_summary')}</p>
    <p><strong>Extraction Confidence:</strong> {payload.get('extraction_confidence')}</p>
    <p><strong>Required Role:</strong> {payload.get('required_role')}</p>
    <p><strong>Escalation Deadline:</strong> {payload.get('escalation_deadline')}</p>
    <ul>{flags_html}</ul>
    <p>
      <a href="{payload.get('approve_url')}">Approve</a> |
      <a href="{payload.get('reject_url')}">Reject</a>
    </p>
    """

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.email_from,
                    "to": [recipient],
                    "subject": f"Approval needed: Invoice {payload.get('invoice_number')}",
                    "html": html,
                },
            )
            response.raise_for_status()
            notification_id = response.json().get("id")
            logger.info(
                "approval_email_sent",
                recipient=recipient,
                notification_id=notification_id,
            )
            return notification_id
    except httpx.HTTPError as exc:
        logger.warning(
            "approval_email_failed",
            recipient=recipient,
            error=str(exc),
        )
        return None


async def send_slack_approval_card(payload: dict[str, Any]) -> str | None:
    settings = get_settings()
    if not settings.slack_webhook_url:
        return None

    flag_lines = "\n".join(
        f"• *{flag.get('type')}* ({flag.get('severity')}): {flag.get('description')}"
        for flag in payload.get("fraud_flags", [])
    ) or "No fraud flags"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Invoice Approval Required"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Vendor:*\n{payload.get('vendor_name')}"},
                {"type": "mrkdwn", "text": f"*Amount:*\n{payload.get('currency')} {payload.get('amount')}"},
                {"type": "mrkdwn", "text": f"*Due Date:*\n{payload.get('due_date') or 'N/A'}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Confidence:*\n{payload.get('extraction_confidence')}",
                },
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Fraud Flags:*\n{flag_lines}"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "url": payload.get("approve_url"),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "url": payload.get("reject_url"),
                },
            ],
        },
    ]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                settings.slack_webhook_url,
                json={"blocks": blocks, "text": "Invoice approval required"},
            )
            response.raise_for_status()
            return str(uuid.uuid4())
    except httpx.HTTPError as exc:
        logger.warning("slack_approval_card_failed", error=str(exc))
        return None
