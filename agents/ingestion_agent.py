"""Ingestion agent — vision LLM invoice extraction."""

from __future__ import annotations

import base64
import json
import re
import uuid
from decimal import Decimal
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from langfuse import get_client
from pydantic import ValidationError
from sqlalchemy import select

from agents.base import BaseAgent
from agents.state import FinFlowState
from core.database import async_session_factory
from core.kafka import TOPIC_INVOICE_EXTRACTED, kafka_producer_manager
from models.invoice import Invoice, InvoiceStatus
from schemas.invoice import ExtractedInvoiceDataWithConfidence
from services.extraction import (
    DocumentPreparationError,
    encode_image_base64,
    prepare_document_for_vision,
)

logger = structlog.get_logger(__name__)

VISION_MODEL = "claude-3-5-sonnet-20241022"
EXTRACTION_CONFIDENCE_THRESHOLD = 0.75
CONFIDENCE_WEIGHTS = {
    "total_amount": 0.30,
    "vendor_name": 0.25,
    "due_date": 0.20,
    "invoice_number": 0.15,
    "line_items": 0.10,
}

EXTRACTION_PROMPT = """You are a precise financial document extraction system.
Extract all invoice fields from this document.
For each field, provide your confidence from 0.0 to 1.0 based on how clearly it appears in the document.
If a field is ambiguous, extract your best guess but give it low confidence.
Return ONLY valid JSON matching this schema exactly:

{schema}

Rules:
- Dates must be ISO format YYYY-MM-DD when present, otherwise null with low confidence.
- Monetary values must be strings representing decimal numbers (e.g. "1234.56").
- line_items.value must be an array of objects with description, quantity, unit_price, total.
- Every top-level field must be an object with "value" and "confidence" keys.
- Do not include markdown fences or commentary.
"""

CORRECTION_PROMPT = """Your previous JSON response failed validation.
Validation errors:
{errors}

Return ONLY corrected JSON matching the schema exactly:
{schema}
"""


class IngestionAgent(BaseAgent):
    @property
    def vision_llm(self):
        litellm_model = f"anthropic/{VISION_MODEL}"
        return self._build_chat_model(litellm_model)

    def build_extraction_prompt(self) -> str:
        schema = json.dumps(
            ExtractedInvoiceDataWithConfidence.model_json_schema(),
            indent=2,
        )
        return EXTRACTION_PROMPT.format(schema=schema)

    def build_correction_prompt(self, errors: str) -> str:
        schema = json.dumps(
            ExtractedInvoiceDataWithConfidence.model_json_schema(),
            indent=2,
        )
        return CORRECTION_PROMPT.format(errors=errors, schema=schema)

    async def call_vision_llm(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
        callbacks: list | None = None,
    ) -> str:
        image_b64 = encode_image_base64(image_bytes)
        media_type = mime_type
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                },
            ]
        )
        response = await self.vision_llm.ainvoke(
            [message],
            config={"callbacks": callbacks or [self.langfuse_callback]},
        )
        return str(response.content)

    def parse_extraction_response(self, raw_response: str) -> ExtractedInvoiceDataWithConfidence:
        payload = _extract_json_object(raw_response)
        return ExtractedInvoiceDataWithConfidence.model_validate(payload)

    async def extract_with_retry(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        invoice_id: str,
        tenant_id: str,
    ) -> tuple[ExtractedInvoiceDataWithConfidence, str, dict[str, Any]]:
        prompt = self.build_extraction_prompt()
        langfuse = get_client()
        trace_metadata = {
            "invoice_id": invoice_id,
            "tenant_id": tenant_id,
            "model": VISION_MODEL,
        }

        with langfuse.start_as_current_observation(
            as_type="generation",
            name="invoice_vision_extraction",
            model=VISION_MODEL,
            input={"prompt": prompt, "mime_type": mime_type},
            metadata=trace_metadata,
        ) as generation:
            raw_response = await self.call_vision_llm(
                prompt=prompt,
                image_bytes=image_bytes,
                mime_type=mime_type,
            )
            try:
                parsed = self.parse_extraction_response(raw_response)
            except ValidationError as first_error:
                correction_prompt = self.build_correction_prompt(str(first_error))
                raw_response = await self.call_vision_llm(
                    prompt=correction_prompt,
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                )
                parsed = self.parse_extraction_response(raw_response)

            confidence_scores = parsed.confidence_map()
            overall_confidence = calculate_overall_confidence(confidence_scores)
            generation.update(
                output={
                    "raw_response": raw_response,
                    "parsed": parsed.model_dump(mode="json"),
                    "confidence_scores": confidence_scores,
                    "overall_confidence": overall_confidence,
                },
                metadata={
                    **trace_metadata,
                    "overall_confidence": overall_confidence,
                },
            )
            langfuse.flush()
            return parsed, raw_response, {
                "confidence_scores": confidence_scores,
                "overall_confidence": overall_confidence,
            }


_agent = IngestionAgent()


def calculate_overall_confidence(confidence_scores: dict[str, float]) -> float:
    total = 0.0
    for field, weight in CONFIDENCE_WEIGHTS.items():
        total += confidence_scores.get(field, 0.0) * weight
    return round(total, 4)


def low_confidence_fields(confidence_scores: dict[str, float], threshold: float = 0.75) -> list[str]:
    return [
        field
        for field in CONFIDENCE_WEIGHTS
        if confidence_scores.get(field, 0.0) < threshold
    ]


def _extract_json_object(raw_response: str) -> dict[str, Any]:
    text = raw_response.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValidationError.from_exception_data(
            "ExtractedInvoiceDataWithConfidence",
            [{"type": "json_invalid", "loc": (), "msg": "No JSON object found", "input": text}],
        )
    return json.loads(text[start : end + 1])


async def _persist_invoice_extraction(
    *,
    invoice_id: str,
    tenant_id: str,
    extracted_data: dict[str, Any],
    confidence_scores: dict[str, float],
    overall_confidence: float,
    requires_human_review: bool,
) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Invoice).where(
                Invoice.id == uuid.UUID(invoice_id),
                Invoice.tenant_id == uuid.UUID(tenant_id),
            )
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            logger.warning("invoice_not_found_for_extraction", invoice_id=invoice_id)
            return

        invoice.invoice_number = extracted_data.get("invoice_number", invoice.invoice_number)
        invoice.amount = Decimal(str(extracted_data.get("total_amount", invoice.amount)))
        invoice.currency = extracted_data.get("currency", invoice.currency)
        if extracted_data.get("due_date"):
            from datetime import date

            invoice.due_date = date.fromisoformat(extracted_data["due_date"])
        invoice.line_items = [
            {
                "description": item["description"],
                "quantity": str(item["quantity"]),
                "unit_price": str(item["unit_price"]),
                "total": str(item["total"]),
            }
            for item in extracted_data.get("line_items", [])
        ]
        invoice.extracted_data = extracted_data
        invoice.extraction_confidence = overall_confidence
        invoice.status = (
            InvoiceStatus.REVIEW_REQUIRED
            if requires_human_review
            else InvoiceStatus.MATCHED
        )
        invoice.flags = {
            **invoice.flags,
            "confidence_scores": confidence_scores,
            "requires_human_review": requires_human_review,
        }
        await session.commit()


async def extract_invoice_node(state: FinFlowState) -> dict:
    update = _agent.log_step(state, "extract")
    invoice_id = state["invoice_id"]
    tenant_id = state["tenant_id"]
    file_type = state.get("file_type", "pdf")
    raw_file_bytes = state.get("raw_file_bytes")

    async with async_session_factory() as session:
        await _agent.update_invoice_status(
            invoice_id,
            InvoiceStatus.EXTRACTING.value,
            db=session,
            tenant_id=tenant_id,
        )
        await session.commit()

    if not raw_file_bytes:
        embedded = (state.get("metadata") or {}).get("file_base64")
        if embedded:
            raw_file_bytes = base64.b64decode(embedded)
        else:
            return {
                **update,
                "error": "missing_file_bytes",
                "requires_human_review": True,
                "review_reason": "No document bytes available for extraction",
            }

    try:
        image_bytes, mime_type = prepare_document_for_vision(raw_file_bytes, file_type)
        parsed, raw_response, metrics = await _agent.extract_with_retry(
            image_bytes=image_bytes,
            mime_type=mime_type,
            invoice_id=invoice_id,
            tenant_id=tenant_id,
        )
    except (DocumentPreparationError, ValidationError, json.JSONDecodeError) as exc:
        logger.exception("invoice_extraction_failed", invoice_id=invoice_id)
        async with async_session_factory() as session:
            await _agent.update_invoice_status(
                invoice_id,
                InvoiceStatus.REVIEW_REQUIRED.value,
                db=session,
                tenant_id=tenant_id,
            )
            await session.commit()
        return {
            **update,
            "error": str(exc),
            "requires_human_review": True,
            "review_reason": f"Extraction failed: {exc}",
        }

    extracted = parsed.to_extracted_data()
    extracted_data = extracted.model_dump(mode="json")
    confidence_scores = metrics["confidence_scores"]
    overall_confidence = metrics["overall_confidence"]
    requires_review = overall_confidence < EXTRACTION_CONFIDENCE_THRESHOLD
    review_reason = ""
    if requires_review:
        low_fields = low_confidence_fields(confidence_scores)
        review_reason = f"Low extraction confidence: {', '.join(low_fields)}"

    await _persist_invoice_extraction(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        extracted_data=extracted_data,
        confidence_scores=confidence_scores,
        overall_confidence=overall_confidence,
        requires_human_review=requires_review,
    )

    if kafka_producer_manager.is_started:
        await kafka_producer_manager.send(
            TOPIC_INVOICE_EXTRACTED,
            {
                "invoice_id": invoice_id,
                "tenant_id": tenant_id,
                "extracted_data": extracted_data,
                "confidence_scores": confidence_scores,
                "overall_confidence": overall_confidence,
                "requires_human_review": requires_review,
                "review_reason": review_reason,
                "raw_response": raw_response,
            },
            key=invoice_id,
        )

    logger.info(
        "invoice_extraction_completed",
        invoice_id=invoice_id,
        overall_confidence=overall_confidence,
        requires_human_review=requires_review,
    )

    return {
        **update,
        "extracted_data": extracted_data,
        "confidence_scores": confidence_scores,
        "requires_human_review": requires_review,
        "review_reason": review_reason,
        "error": "",
        "metadata": {
            **(state.get("metadata") or {}),
            "overall_confidence": overall_confidence,
            "vision_model": VISION_MODEL,
        },
    }


async def extract_from_kafka_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Run ingestion extraction from a Kafka invoice.received payload."""
    file_b64 = payload.get("file_base64")
    if not file_b64:
        raise ValueError("Missing file_base64 in payload")

    content_type = payload.get("content_type", "application/pdf")
    file_type = "pdf" if "pdf" in content_type else "png"
    state: FinFlowState = {
        "invoice_id": payload["invoice_id"],
        "tenant_id": payload["tenant_id"],
        "raw_file_bytes": base64.b64decode(file_b64),
        "file_type": file_type,
        "step_history": [],
        "metadata": payload,
    }
    result = await extract_invoice_node(state)
    if result.get("error"):
        raise ValueError(result["error"])
    overall = (result.get("metadata") or {}).get("overall_confidence", 0.0)
    return result.get("extracted_data") or {}, float(overall)
