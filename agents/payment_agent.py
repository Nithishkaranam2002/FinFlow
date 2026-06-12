"""Payment scheduling agent with LLM-generated payment memos."""

from __future__ import annotations

import structlog

from agents.base import BaseAgent
from agents.state import FinFlowState
from core.observability import trace_agent_step

logger = structlog.get_logger(__name__)


class PaymentAgent(BaseAgent):
    agent_name = "payment"

    async def generate_payment_memo(
        self,
        *,
        tenant_id: str,
        invoice_id: str,
        vendor_name: str,
        amount: str,
        currency: str,
    ) -> str:
        response = await self.invoke_llm_with_routing_context(
            [
                {
                    "role": "user",
                    "content": (
                        "Write a concise payment memo (max 120 chars) for an AP payment run. "
                        f"Vendor: {vendor_name}. Amount: {currency} {amount}."
                    ),
                }
            ],
            task_type="payment_memo",
            tenant_id=tenant_id,
            invoice_id=invoice_id,
        )
        return response.content.strip()[:120]


_agent = PaymentAgent()


@trace_agent_step("payment")
async def enrich_payment_metadata_node(state: FinFlowState) -> dict:
    """Optional graph node: attach an LLM payment memo before scheduling."""
    update = _agent.log_step(state, "payment_memo")
    extracted = state.get("extracted_data") or {}
    vendor_name = (state.get("vendor_match") or {}).get("matched_name") or extracted.get(
        "vendor_name", "Vendor"
    )
    amount = str(extracted.get("total_amount", "0"))
    currency = extracted.get("currency", "USD")

    memo = await _agent.generate_payment_memo(
        tenant_id=state["tenant_id"],
        invoice_id=state["invoice_id"],
        vendor_name=vendor_name,
        amount=amount,
        currency=currency,
    )

    return {
        **update,
        "metadata": {
            **(state.get("metadata") or {}),
            "payment_memo": memo,
        },
    }
