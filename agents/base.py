"""Base class shared by all FinFlow agents."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from core.observability import get_langfuse_callback_handler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.state import FinFlowState
from core.config import Settings, get_settings
from core.llm_gateway import LLMGateway, LLMResponse, build_routing_context, get_llm_gateway

logger = structlog.get_logger(__name__)


class BaseAgent:
    """Shared LLM gateway, tracing, logging, and persistence utilities for FinFlow agents."""

    agent_name: str = "base"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def gateway(self) -> LLMGateway:
        return get_llm_gateway()

    async def invoke_llm(
        self,
        messages: list[Any],
        *,
        task_type: str,
        tenant_id: str,
        invoice_id: str | None = None,
        context: dict[str, Any] | None = None,
        tier: str | None = None,
    ) -> LLMResponse:
        return await self.gateway.acompletion(
            messages=messages,
            task_type=task_type,
            agent_name=self.agent_name,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            context=context,
            tier=tier,
        )

    async def invoke_llm_with_routing_context(
        self,
        messages: list[Any],
        *,
        task_type: str,
        tenant_id: str,
        invoice_id: str | None = None,
        vendor_id: str | None = None,
        is_vision: bool = False,
        risk_score: float = 0.0,
        extra_context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        context = await build_routing_context(
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            is_vision=is_vision,
            risk_score=risk_score,
        )
        if extra_context:
            context.update(extra_context)
        return await self.invoke_llm(
            messages,
            task_type=task_type,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            context=context,
        )

    def langfuse_callback(
        self,
        *,
        tenant_id: str = "unknown",
        invoice_id: str = "unknown",
    ):
        """Langfuse tracing callback for LangChain/LangGraph runs."""
        return get_langfuse_callback_handler(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            agent_name=self.agent_name,
        )

    def log_step(self, state: FinFlowState, step_name: str, **kwargs: Any) -> dict[str, Any]:
        """Append to step_history and emit a structured log entry."""
        logger.info(
            "agent_step",
            step=step_name,
            invoice_id=state.get("invoice_id"),
            tenant_id=state.get("tenant_id"),
            **kwargs,
        )
        return {"step_history": [step_name]}

    async def update_invoice_status(
        self,
        invoice_id: str,
        status: str,
        db: AsyncSession,
        *,
        tenant_id: str | None = None,
    ) -> None:
        """Persist invoice status changes to PostgreSQL."""
        from models.invoice import Invoice, InvoiceStatus

        query = select(Invoice).where(Invoice.id == uuid.UUID(invoice_id))
        if tenant_id:
            query = query.where(Invoice.tenant_id == uuid.UUID(tenant_id))

        result = await db.execute(query)
        invoice = result.scalar_one_or_none()
        if invoice is None:
            logger.warning(
                "invoice_status_update_skipped",
                invoice_id=invoice_id,
                status=status,
                reason="not_found",
            )
            return

        invoice.status = InvoiceStatus(status)
        await db.flush()
        logger.info(
            "invoice_status_updated",
            invoice_id=invoice_id,
            status=status,
        )
