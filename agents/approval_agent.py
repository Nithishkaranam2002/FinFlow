"""Approval orchestration nodes for the FinFlow LangGraph pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from langgraph.types import interrupt
from sqlalchemy import select

from agents.base import BaseAgent
from agents.state import FinFlowState, min_confidence_score
from core.database import async_session_factory
from core.observability import trace_agent_step
from core.tenant import set_current_tenant_id
from models.invoice import Invoice, InvoiceStatus
from models.tenant import Tenant
from models.user import User, UserRole
from services.approval_policy import resolve_required_role
from services.audit import log_audit_event
from services.notifications import (
    build_approval_payload,
    send_approval_email,
    send_slack_approval_card,
)

logger = structlog.get_logger(__name__)


class ApprovalAgent(BaseAgent):
    agent_name = "approval"


_agent = ApprovalAgent()

ESCALATION_HOURS = 48
MAX_ESCALATIONS = 3


async def _load_tenant_config(tenant_id: str) -> dict[str, Any]:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
        )
        tenant = result.scalar_one_or_none()
        return tenant.config if tenant else {}


async def _find_users_for_role(tenant_id: str, required_role: str) -> list[User]:
    async with async_session_factory() as db:
        set_current_tenant_id(uuid.UUID(tenant_id))
        result = await db.execute(
            select(User).where(
                User.tenant_id == uuid.UUID(tenant_id),
                User.role == UserRole(required_role),
                User.is_active.is_(True),
            )
        )
        return list(result.scalars().all())


@trace_agent_step("approval")
async def route_approval_node(state: FinFlowState) -> dict:
    """Resolve approval policy and identify approvers for this invoice."""
    update = _agent.log_step(state, "route_approval")
    extracted = state.get("extracted_data") or {}
    amount = Decimal(str(extracted.get("total_amount", 0) or 0))
    fraud_flags = state.get("fraud_flags") or []

    tenant_config = await _load_tenant_config(state["tenant_id"])
    required_role, auto_approve = resolve_required_role(
        amount, fraud_flags, tenant_config
    )

    metadata = {
        **(state.get("metadata") or {}),
        "required_role": required_role,
        "auto_approve": auto_approve,
    }

    if auto_approve:
        async with async_session_factory() as db:
            set_current_tenant_id(uuid.UUID(state["tenant_id"]))
            await _agent.update_invoice_status(
                state["invoice_id"],
                InvoiceStatus.APPROVED.value,
                db,
                tenant_id=state["tenant_id"],
            )
            await log_audit_event(
                db,
                tenant_id=uuid.UUID(state["tenant_id"]),
                entity_type="invoice",
                entity_id=uuid.UUID(state["invoice_id"]),
                action="auto_approved",
                actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                actor_role="system",
                new_value={"approval_status": "approved", "auto_approve": True},
            )
            await db.commit()

        return {
            **update,
            "approval_status": "approved",
            "metadata": metadata,
        }

    approvers = await _find_users_for_role(state["tenant_id"], required_role)
    approver_emails = [user.email for user in approvers]

    if not approver_emails:
        logger.warning(
            "no_approvers_found",
            tenant_id=state["tenant_id"],
            required_role=required_role,
            invoice_id=state["invoice_id"],
        )

    return {
        **update,
        "approval_status": "pending",
        "metadata": {
            **metadata,
            "approver_emails": approver_emails,
            "approver_ids": [str(user.id) for user in approvers],
        },
    }


@trace_agent_step("approval")
async def send_approval_notification_node(state: FinFlowState) -> dict:
    """Notify approvers and mark the invoice as pending approval."""
    update = _agent.log_step(state, "send_approval_notification")
    metadata = state.get("metadata") or {}
    required_role = metadata.get("required_role", UserRole.APPROVER.value)
    approver_emails = metadata.get("approver_emails") or []
    invoice_id = state["invoice_id"]
    thread_id = invoice_id

    confidence = (state.get("metadata") or {}).get("overall_confidence")
    if confidence is None:
        confidence = min_confidence_score(state.get("confidence_scores"))

    payload = build_approval_payload(
        invoice_id=invoice_id,
        tenant_id=state["tenant_id"],
        extracted_data=state.get("extracted_data") or {},
        fraud_flags=state.get("fraud_flags") or [],
        extraction_confidence=confidence,
        required_role=required_role,
        vendor_match=state.get("vendor_match"),
    )

    notification_ids: list[str] = []
    for email in approver_emails:
        notification_id = await send_approval_email(email, payload)
        if notification_id:
            notification_ids.append(notification_id)

    slack_id = await send_slack_approval_card(payload)
    if slack_id:
        notification_ids.append(slack_id)

    pending_since = datetime.now(timezone.utc).isoformat()
    async with async_session_factory() as db:
        set_current_tenant_id(uuid.UUID(state["tenant_id"]))
        result = await db.execute(
            select(Invoice).where(Invoice.id == uuid.UUID(invoice_id))
        )
        invoice = result.scalar_one_or_none()
        if invoice:
            invoice.status = InvoiceStatus.PENDING_APPROVAL
            invoice.flags = {
                **(invoice.flags or {}),
                "required_role": required_role,
                "thread_id": thread_id,
                "notification_ids": notification_ids,
                "pending_since": pending_since,
                "escalation_count": invoice.flags.get("escalation_count", 0),
                "fraud_flags": state.get("fraud_flags") or [],
                "approval_payload": payload,
            }
            await db.commit()

    return {
        **update,
        "approval_status": "pending",
        "metadata": {
            **metadata,
            "thread_id": thread_id,
            "notification_ids": notification_ids,
            "pending_since": pending_since,
            "approval_payload": payload,
        },
    }


@trace_agent_step("approval")
async def await_approval_node(state: FinFlowState) -> dict:
    """Human-in-the-loop interrupt; resumes when approver calls the API."""
    update = _agent.log_step(state, "await_approval")

    payload = (state.get("metadata") or {}).get("approval_payload") or {
        "invoice_id": state.get("invoice_id"),
        "required_role": (state.get("metadata") or {}).get("required_role"),
        "fraud_flags": state.get("fraud_flags", []),
    }

    decision = interrupt(payload)
    if not isinstance(decision, dict):
        decision = {"decision": str(decision)}

    decision_value = decision.get("decision", "pending")
    approver_id = decision.get("approver_id", "")
    notes = decision.get("notes", "")

    approval_status = "approved" if decision_value == "approved" else "rejected"
    if decision_value not in {"approved", "rejected"}:
        approval_status = "pending"

    invoice_status = (
        InvoiceStatus.APPROVED
        if approval_status == "approved"
        else InvoiceStatus.REJECTED
    )

    async with async_session_factory() as db:
        set_current_tenant_id(uuid.UUID(state["tenant_id"]))
        result = await db.execute(
            select(Invoice).where(Invoice.id == uuid.UUID(state["invoice_id"]))
        )
        invoice = result.scalar_one_or_none()
        old_status = invoice.status.value if invoice else None

        if invoice:
            invoice.status = invoice_status
            invoice.flags = {
                **(invoice.flags or {}),
                "approver_id": approver_id,
                "approval_notes": notes,
                "approval_decision_at": datetime.now(timezone.utc).isoformat(),
            }

        await log_audit_event(
            db,
            tenant_id=uuid.UUID(state["tenant_id"]),
            entity_type="invoice",
            entity_id=uuid.UUID(state["invoice_id"]),
            action=f"approval_{decision_value}",
            actor_id=uuid.UUID(approver_id),
            actor_role=decision.get("approver_role")
            or (state.get("metadata") or {}).get("required_role", "approver"),
            old_value={"status": old_status},
            new_value={
                "status": invoice_status.value,
                "approval_status": approval_status,
                "approver_id": approver_id,
            },
            reason=notes or None,
        )
        await db.commit()

    logger.info(
        "approval_decision_recorded",
        invoice_id=state["invoice_id"],
        decision=decision_value,
        approver_id=approver_id,
    )

    return {
        **update,
        "approval_status": approval_status,
        "approver_id": approver_id,
        "approval_notes": notes,
    }


async def escalation_check_node() -> dict[str, Any]:
    """
    Hourly Celery task: escalate stale pending approvals.

    After 48 hours without response, notify the controller.
    After 3 escalations, reassign to the auditor role.
    """
    from datetime import timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core.config import get_settings

    settings = get_settings()
    sync_engine = create_engine(settings.database_sync_url)
    SyncSession = sessionmaker(bind=sync_engine)

    now = datetime.now(timezone.utc)
    deadline = now - timedelta(hours=ESCALATION_HOURS)
    escalated: list[str] = []

    with SyncSession() as db:
        invoices = (
            db.query(Invoice)
            .filter(Invoice.status == InvoiceStatus.PENDING_APPROVAL)
            .all()
        )

        for invoice in invoices:
            flags = invoice.flags or {}
            pending_since_raw = flags.get("pending_since")
            if not pending_since_raw:
                continue

            pending_since = datetime.fromisoformat(pending_since_raw)
            if pending_since.tzinfo is None:
                pending_since = pending_since.replace(tzinfo=timezone.utc)

            if pending_since > deadline:
                continue

            escalation_count = int(flags.get("escalation_count", 0)) + 1
            required_role = flags.get("required_role", UserRole.APPROVER.value)

            if escalation_count >= MAX_ESCALATIONS:
                required_role = UserRole.AUDITOR.value
                flags["required_role"] = required_role
                flags["auto_escalated_to_auditor"] = True

            flags["escalation_count"] = escalation_count
            flags["last_escalation_at"] = now.isoformat()
            invoice.flags = flags
            db.flush()

            extracted = invoice.extracted_data or {}
            payload = build_approval_payload(
                invoice_id=str(invoice.id),
                tenant_id=str(invoice.tenant_id),
                extracted_data=extracted,
                fraud_flags=flags.get("fraud_flags") or [],
                extraction_confidence=invoice.extraction_confidence,
                required_role=required_role,
            )

            controllers = (
                db.query(User)
                .filter(
                    User.tenant_id == invoice.tenant_id,
                    User.role == UserRole(required_role),
                    User.is_active.is_(True),
                )
                .all()
            )

            for user in controllers:
                await send_approval_email(
                    user.email,
                    {
                        **payload,
                        "escalation_count": escalation_count,
                        "escalation_message": (
                            f"Approval overdue ({escalation_count}/{MAX_ESCALATIONS}). "
                            f"Escalation deadline was {ESCALATION_HOURS} hours ago."
                        ),
                    },
                )

            escalated.append(str(invoice.id))

        db.commit()

    logger.info("approval_escalation_check_complete", escalated_count=len(escalated))
    return {"escalated_invoice_ids": escalated, "count": len(escalated)}
