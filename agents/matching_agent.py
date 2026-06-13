"""Matching and fraud detection agent nodes."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import BaseAgent
from agents.state import FinFlowState
from core.database import async_session_factory
from core.observability import trace_agent_step
from models.invoice import Invoice, InvoiceStatus
from models.vendor import Vendor
from services.audit import log_audit_event
from services.fraud_detection import run_fraud_checks
from services.matching import VendorMatchResult, match_vendor_by_name

logger = structlog.get_logger(__name__)

SYSTEM_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class MatchingAgent(BaseAgent):
    agent_name = "matching"


_agent = MatchingAgent()


@trace_agent_step("matching")
async def match_vendor_node(state: FinFlowState) -> dict:
    update = _agent.log_step(state, "match_vendor")
    tenant_id = uuid.UUID(state["tenant_id"])
    extracted = state.get("extracted_data") or {}
    extracted_vendor_name = extracted.get("vendor_name", "")
    vendor_id_hint = (state.get("metadata") or {}).get("vendor_id")

    async with async_session_factory() as session:
        result = await session.execute(
            select(Vendor).where(
                Vendor.tenant_id == tenant_id,
                Vendor.is_active.is_(True),
            )
        )
        vendors = list(result.scalars().all())

        if vendor_id_hint:
            selected_vendor = next(
                (vendor for vendor in vendors if str(vendor.id) == str(vendor_id_hint)),
                None,
            )
            if selected_vendor:
                match_result = VendorMatchResult(
                    vendor_match={
                        "vendor_id": str(selected_vendor.id),
                        "matched_name": selected_vendor.name,
                        "extracted_name": extracted_vendor_name or selected_vendor.name,
                        "match_confidence": 100.0,
                        "match_method": "upload_vendor_id",
                        "email": selected_vendor.email,
                        "payment_terms_days": selected_vendor.payment_terms_days,
                    },
                    match_confidence=100.0,
                    requires_human_review=False,
                    review_reason="",
                    fraud_flags=[],
                    matched_vendor=selected_vendor,
                )
            else:
                match_result = match_vendor_by_name(extracted_vendor_name, vendors)
        else:
            match_result = match_vendor_by_name(extracted_vendor_name, vendors)

        if match_result.matched_vendor and match_result.match_confidence and match_result.match_confidence >= 65:
            await _update_invoice_vendor(
                session,
                invoice_id=uuid.UUID(state["invoice_id"]),
                tenant_id=tenant_id,
                vendor_id=match_result.matched_vendor.id,
            )

        await session.commit()

    if vendor_id_hint and match_result.matched_vendor and (
        (match_result.vendor_match or {}).get("match_method") == "upload_vendor_id"
    ):
        combined_flags = list(match_result.fraud_flags)
        requires_review = match_result.requires_human_review
        review_reason = match_result.review_reason or ""
    else:
        existing_flags = list(state.get("fraud_flags") or [])
        combined_flags = existing_flags + match_result.fraud_flags
        requires_review = state.get("requires_human_review", False) or match_result.requires_human_review
        review_reason = match_result.review_reason or state.get("review_reason", "")

    return {
        **update,
        "vendor_match": match_result.vendor_match,
        "po_match": None,
        "fraud_flags": combined_flags,
        "requires_human_review": requires_review,
        "review_reason": review_reason,
        "metadata": {
            **(state.get("metadata") or {}),
            "vendor_match_confidence": match_result.match_confidence,
        },
    }


@trace_agent_step("matching")
async def check_fraud_node(state: FinFlowState) -> dict:
    update = _agent.log_step(state, "check_fraud")
    tenant_id = uuid.UUID(state["tenant_id"])
    invoice_id = uuid.UUID(state["invoice_id"])
    extracted = state.get("extracted_data") or {}
    vendor_match = state.get("vendor_match") or {}

    amount = Decimal(str(extracted.get("total_amount", "0")))
    invoice_number = extracted.get("invoice_number", "")
    invoice_date_raw = extracted.get("invoice_date")
    invoice_date = date.fromisoformat(invoice_date_raw) if invoice_date_raw else None
    vendor_id = uuid.UUID(vendor_match["vendor_id"]) if vendor_match.get("vendor_id") else None

    async with async_session_factory() as session:
        fraud_result = await run_fraud_checks(
            session,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            vendor_id=vendor_id,
            invoice_number=invoice_number,
            amount=amount,
            invoice_date=invoice_date,
            existing_flags=list(state.get("fraud_flags") or []),
        )

        await _persist_fraud_results(
            session,
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            fraud_flags=fraud_result.fraud_flags,
            overall_risk_score=fraud_result.overall_risk_score,
        )

        for flag in fraud_result.fraud_flags:
            await log_audit_event(
                session,
                tenant_id=tenant_id,
                entity_type="invoice",
                entity_id=invoice_id,
                action="fraud_flag_raised",
                actor_id=SYSTEM_ACTOR_ID,
                actor_role="system",
                new_value=flag,
                reason=flag.get("description"),
            )

        await session.commit()

    requires_review = state.get("requires_human_review", False) or fraud_result.requires_human_review
    review_reason = state.get("review_reason", "")
    if fraud_result.requires_human_review and not review_reason:
        review_reason = (
            f"Fraud risk score {fraud_result.overall_risk_score:.2f} exceeds review threshold"
        )

    approval_status = state.get("approval_status")
    if fraud_result.approval_status == "auto_rejected":
        approval_status = "auto_rejected"
        requires_review = True
        review_reason = review_reason or "Invoice auto-rejected due to critical fraud risk"

    if fraud_result.overall_risk_score > 0.5:
        summary = await _agent.invoke_llm_with_routing_context(
            [
                {
                    "role": "user",
                    "content": (
                        "Summarize these invoice fraud flags for a finance controller in one sentence. "
                        f"Flags: {json.dumps(fraud_result.fraud_flags)} "
                        f"Risk score: {fraud_result.overall_risk_score:.2f}"
                    ),
                }
            ],
            task_type="fraud_judgment",
            tenant_id=str(tenant_id),
            invoice_id=str(invoice_id),
            risk_score=fraud_result.overall_risk_score,
        )
        review_reason = review_reason or summary.content

    logger.info(
        "fraud_checks_completed",
        invoice_id=str(invoice_id),
        flag_count=len(fraud_result.fraud_flags),
        overall_risk_score=fraud_result.overall_risk_score,
    )

    return {
        **update,
        "fraud_flags": fraud_result.fraud_flags,
        "overall_risk_score": fraud_result.overall_risk_score,
        "requires_human_review": requires_review,
        "review_reason": review_reason,
        "approval_status": approval_status or state.get("approval_status", ""),
    }


async def _update_invoice_vendor(
    session: AsyncSession,
    *,
    invoice_id: uuid.UUID,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        return
    invoice.vendor_id = vendor_id
    invoice.status = InvoiceStatus.MATCHED
    await session.flush()


async def _persist_fraud_results(
    session: AsyncSession,
    *,
    invoice_id: uuid.UUID,
    tenant_id: uuid.UUID,
    fraud_flags: list[dict[str, Any]],
    overall_risk_score: float,
) -> None:
    result = await session.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        return

    invoice.flags = {
        **invoice.flags,
        "fraud_flags": fraud_flags,
        "overall_risk_score": overall_risk_score,
    }
    if overall_risk_score > 0.7:
        invoice.status = InvoiceStatus.MATCHED
    await session.flush()
