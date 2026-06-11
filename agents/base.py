"""Base class shared by all FinFlow agents."""

from __future__ import annotations

import os
import uuid
from functools import lru_cache
from typing import Any

import structlog
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.state import FinFlowState
from core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class BaseAgent:
    """Shared LLM, tracing, logging, and persistence utilities for FinFlow agents."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    @lru_cache
    def _litellm_base_url() -> str | None:
        return os.getenv("LITELLM_API_BASE")

    def _build_chat_model(self, model: str) -> ChatOpenAI:
        litellm_base = self._litellm_base_url()
        if litellm_base:
            return ChatOpenAI(
                model=model,
                api_key=self.settings.litellm_master_key,
                base_url=f"{litellm_base.rstrip('/')}/v1",
                temperature=0,
            )

        api_key = self.settings.openai_api_key or self.settings.anthropic_api_key
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0,
        )

    @property
    def llm(self) -> ChatOpenAI:
        """Primary model for routine agent tasks (LiteLLM-routed when configured)."""
        return self._build_chat_model(self.settings.primary_model)

    @property
    def premium_llm(self) -> ChatOpenAI:
        """Premium model for complex reasoning and approval decisions."""
        return self._build_chat_model(self.settings.premium_model)

    @property
    def langfuse_callback(self) -> CallbackHandler:
        """Langfuse tracing callback for LangChain/LangGraph runs."""
        return CallbackHandler(
            public_key=self.settings.langfuse_public_key,
            secret_key=self.settings.langfuse_secret_key,
            host=str(self.settings.langfuse_host),
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
