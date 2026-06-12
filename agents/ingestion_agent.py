"""Ingestion agent — vision LLM invoice extraction."""

from __future__ import annotations

import base64
import json
import re
import uuid
from decimal import Decimal
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import select

from agents.base import BaseAgent
from agents.state import FinFlowState
from core.database import async_session_factory
from core.kafka import TOPIC_INVOICE_EXTRACTED, kafka_producer_manager
from core.llm_gateway import VISION_MODEL
from core.observability import extract_trace_ids, get_langfuse_client, trace_agent_step
from langfuse import propagate_attributes
from models.invoice import Invoice, InvoiceStatus
from schemas.invoice import ExtractedInvoiceDataWithConfidence
from services.audit import log_audit_event
from services.extraction import (
    DocumentPreparationError,
    encode_image_base64,
    prepare_document_for_vision,
)
from services.extraction_quality import persist_extraction_trace_metadata
from services.mem0_corrections import fetch_vendor_correction_examples

logger = structlog.get_logger(__name__)

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
    agent_name = "ingestion"

    def build_extraction_prompt(
        self,
        extraction_prior: dict[str, Any] | None = None,
        few_shot_examples: list[dict[str, Any]] | None = None,
    ) -> str:
        schema = json.dumps(
            ExtractedInvoiceDataWithConfidence.model_json_schema(),
            indent=2,
        )
        prompt = EXTRACTION_PROMPT.format(schema=schema)
        if few_shot_examples:
            prompt += (
                "\n\nFew-shot correction examples from human reviewers for this vendor "
                "(apply formatting patterns, not literal values unless the document matches):\n"
                f"{json.dumps(few_shot_examples, indent=2)}"
            )
        if extraction_prior:
            prompt += (
                "\n\nPrior extraction pattern from a very similar document for this vendor "
                f"(use as a strong prior, not ground truth):\n{json.dumps(extraction_prior, indent=2)}"
            )
        return prompt

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
        tenant_id: str,
        invoice_id: str,
        vendor_id: str | None = None,
        document_bytes: bytes | None = None,
        extraction_prior: dict[str, Any] | None = None,
    ) -> str:
        image_b64 = encode_image_base64(image_bytes)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                    },
                ],
            }
        ]

        if document_bytes and vendor_id:
            response = await self.gateway.acompletion_with_semantic_cache(
                messages=messages,
                task_type="vision_extraction",
                agent_name=self.agent_name,
                tenant_id=tenant_id,
                vendor_id=vendor_id,
                document_bytes=document_bytes,
                invoice_id=invoice_id,
                context={
                    "is_vision": True,
                    "known_vendor": True,
                    "first_time_vendor": False,
                    "vendor_confidence_hint": 0.95 if extraction_prior else 0.0,
                },
            )
        else:
            response = await self.invoke_llm_with_routing_context(
                messages,
                task_type="vision_extraction",
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                vendor_id=vendor_id,
                is_vision=True,
            )

        return response.content

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
        vendor_id: str | None = None,
        raw_file_bytes: bytes | None = None,
    ) -> tuple[ExtractedInvoiceDataWithConfidence, str, dict[str, Any]]:
        extraction_prior: dict[str, Any] | None = None
        cache_hit: dict[str, Any] | None = None
        if vendor_id and raw_file_bytes:
            cache_hit = await self.gateway.semantic_cache.lookup(
                tenant_id=tenant_id,
                vendor_id=vendor_id,
                document_bytes=raw_file_bytes,
            )
            if cache_hit:
                extraction_prior = cache_hit.get("extraction_pattern")

        few_shot_examples: list[dict[str, Any]] = []
        if vendor_id:
            few_shot_examples = await fetch_vendor_correction_examples(
                tenant_id,
                vendor_id,
            )

        prompt = self.build_extraction_prompt(extraction_prior, few_shot_examples)
        langfuse = get_langfuse_client()
        trace_metadata = {
            "invoice_id": invoice_id,
            "tenant_id": tenant_id,
            "agent_name": self.agent_name,
            "gateway": True,
        }

        with propagate_attributes(
            tags=[
                f"tenant_id:{tenant_id}",
                f"invoice_id:{invoice_id}",
                f"agent_name:{self.agent_name}",
            ],
            metadata=trace_metadata,
            trace_name="ingestion.invoice_vision_extraction",
        ):
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
                    tenant_id=tenant_id,
                    invoice_id=invoice_id,
                    vendor_id=vendor_id,
                    document_bytes=raw_file_bytes or image_bytes,
                )
                try:
                    parsed = self.parse_extraction_response(raw_response)
                except ValidationError as first_error:
                    correction_prompt = self.build_correction_prompt(str(first_error))
                    raw_response = await self.call_vision_llm(
                        prompt=correction_prompt,
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                        tenant_id=tenant_id,
                        invoice_id=invoice_id,
                        vendor_id=vendor_id,
                        document_bytes=raw_file_bytes or image_bytes,
                    )
                    try:
                        parsed = self.parse_extraction_response(raw_response)
                    except ValidationError as second_error:
                        return None, raw_response, _validation_fallback_metrics(
                            raw_response,
                            str(second_error),
                        )

                parsed, line_item_notes = _adjust_line_item_confidence(parsed)
                confidence_scores = parsed.confidence_map()
                overall_confidence = calculate_overall_confidence(confidence_scores)
                if extraction_prior:
                    boost = float((cache_hit or {}).get("confidence_boost", 0.05))
                    overall_confidence = min(1.0, round(overall_confidence + boost, 4))
                    for field in confidence_scores:
                        confidence_scores[field] = min(
                            1.0, round(confidence_scores[field] + boost / 2, 4)
                        )
                if vendor_id and raw_file_bytes:
                    await self.gateway.store_extraction_pattern(
                        tenant_id=tenant_id,
                        vendor_id=vendor_id,
                        document_bytes=raw_file_bytes,
                        extraction_pattern=parsed.model_dump(mode="json"),
                    )

                trace_ids = extract_trace_ids()
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
                        **trace_ids,
                    },
                )
                langfuse.flush()
                return parsed, raw_response, {
                    "confidence_scores": confidence_scores,
                    "overall_confidence": overall_confidence,
                    "line_item_notes": line_item_notes,
                    "langfuse_trace_id": trace_ids.get("trace_id"),
                    "langfuse_observation_id": trace_ids.get("observation_id"),
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


def _adjust_line_item_confidence(
    parsed: ExtractedInvoiceDataWithConfidence,
) -> tuple[ExtractedInvoiceDataWithConfidence, list[str]]:
    """Lower line_items confidence when price breakdown fields are missing."""
    notes: list[str] = []
    items = parsed.line_items.value or []
    for index, item in enumerate(items, start=1):
        if any(
            getattr(item, field) is None
            for field in ("quantity", "unit_price", "total")
        ):
            notes.append(f"Line item {index} missing price breakdown")
    if notes:
        parsed.line_items.confidence = min(parsed.line_items.confidence, 0.4)
    return parsed, notes


def _validation_fallback_metrics(
    raw_response: str,
    validation_error: str,
) -> dict[str, Any]:
    try:
        raw_payload = _extract_json_object(raw_response)
    except (ValidationError, json.JSONDecodeError):
        raw_payload = {"unparsed_response": raw_response}

    return {
        "is_fallback": True,
        "fallback_extracted_data": {
            "_raw_llm_response": raw_payload,
            "_validation_error": validation_error,
        },
        "confidence_scores": {field: 0.3 for field in CONFIDENCE_WEIGHTS},
        "overall_confidence": 0.3,
        "review_reason": "Extraction validation failed - manual review needed",
        "line_item_notes": [],
        "raw_response": raw_response,
    }


def _serialize_line_items(line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in line_items:
        serialized.append(
            {
                "description": item.get("description", ""),
                "quantity": str(item["quantity"])
                if item.get("quantity") is not None
                else None,
                "unit_price": str(item["unit_price"])
                if item.get("unit_price") is not None
                else None,
                "total": str(item["total"]) if item.get("total") is not None else None,
            }
        )
    return serialized


async def _log_validation_fallback_audit(
    *,
    invoice_id: str,
    tenant_id: str,
    raw_response: str,
    validation_error: str,
    fallback_extracted_data: dict[str, Any],
) -> None:
    async with async_session_factory() as session:
        await log_audit_event(
            session,
            tenant_id=uuid.UUID(tenant_id),
            entity_type="invoice",
            entity_id=uuid.UUID(invoice_id),
            action="extraction_validation_fallback",
            actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            actor_role="system",
            reason=validation_error,
            new_value={
                "raw_llm_response": raw_response,
                "fallback_extracted_data": fallback_extracted_data,
            },
        )
        await session.commit()


async def _persist_invoice_extraction(
    *,
    invoice_id: str,
    tenant_id: str,
    extracted_data: dict[str, Any],
    confidence_scores: dict[str, float],
    overall_confidence: float,
    requires_human_review: bool,
    review_reason: str = "",
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
        total_amount = extracted_data.get("total_amount")
        if total_amount is not None:
            invoice.amount = Decimal(str(total_amount))
        invoice.currency = extracted_data.get("currency", invoice.currency)
        if extracted_data.get("due_date"):
            from datetime import date

            invoice.due_date = date.fromisoformat(extracted_data["due_date"])
        invoice.line_items = _serialize_line_items(extracted_data.get("line_items", []))
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
            "review_reason": review_reason,
        }
        await session.commit()


@trace_agent_step("ingestion")
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
            vendor_id=(state.get("metadata") or {}).get("vendor_id"),
            raw_file_bytes=raw_file_bytes,
        )
    except (DocumentPreparationError, json.JSONDecodeError) as exc:
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

    if metrics.get("is_fallback"):
        extracted_data = metrics["fallback_extracted_data"]
        confidence_scores = metrics["confidence_scores"]
        overall_confidence = metrics["overall_confidence"]
        requires_review = True
        review_reason = metrics["review_reason"]

        await _log_validation_fallback_audit(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            raw_response=raw_response,
            validation_error=extracted_data.get("_validation_error", ""),
            fallback_extracted_data=extracted_data,
        )
        await _persist_invoice_extraction(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            extracted_data=extracted_data,
            confidence_scores=confidence_scores,
            overall_confidence=overall_confidence,
            requires_human_review=requires_review,
            review_reason=review_reason,
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
                    "validation_fallback": True,
                },
                key=invoice_id,
            )

        logger.warning(
            "invoice_extraction_validation_fallback",
            invoice_id=invoice_id,
            overall_confidence=overall_confidence,
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
                "validation_fallback": True,
            },
        }

    assert parsed is not None
    extracted = parsed.to_extracted_data()
    extracted_data = extracted.model_dump(mode="json")
    confidence_scores = metrics["confidence_scores"]
    overall_confidence = metrics["overall_confidence"]
    requires_review = overall_confidence < EXTRACTION_CONFIDENCE_THRESHOLD
    review_reason_parts: list[str] = list(metrics.get("line_item_notes") or [])
    if requires_review:
        low_fields = low_confidence_fields(confidence_scores)
        review_reason_parts.append(f"Low extraction confidence: {', '.join(low_fields)}")
    review_reason = "; ".join(review_reason_parts)

    await _persist_invoice_extraction(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        extracted_data=extracted_data,
        confidence_scores=confidence_scores,
        overall_confidence=overall_confidence,
        requires_human_review=requires_review,
        review_reason=review_reason,
    )

    async with async_session_factory() as session:
        await persist_extraction_trace_metadata(
            session,
            invoice_id=uuid.UUID(invoice_id),
            tenant_id=uuid.UUID(tenant_id),
            trace_id=metrics.get("langfuse_trace_id"),
            observation_id=metrics.get("langfuse_observation_id"),
        )
        await session.commit()

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
            "llm_gateway": True,
            "langfuse_trace_id": metrics.get("langfuse_trace_id"),
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
    if result.get("error") and not result.get("extracted_data"):
        raise ValueError(result["error"])
    overall = (result.get("metadata") or {}).get("overall_confidence", 0.0)
    return result.get("extracted_data") or {}, float(overall)
