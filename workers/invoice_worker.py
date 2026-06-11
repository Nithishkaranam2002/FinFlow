#!/usr/bin/env python3
"""Kafka consumer worker for invoice.received events."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from decimal import Decimal

import structlog
from aiokafka import AIOKafkaConsumer
from sqlalchemy import select

from core.config import get_settings
from core.database import async_session_factory
from core.kafka import (
    TOPIC_INVOICE_EXTRACTED,
    TOPIC_INVOICE_RECEIVED,
    KafkaProducerManager,
)
from models.invoice import Invoice, InvoiceStatus
from services.audit import log_audit_event
from services.extraction import ExtractionError, extract_invoice

logger = structlog.get_logger(__name__)

CONSUMER_GROUP = "finflow-invoice-workers"
SYSTEM_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def process_invoice_received(
    message_value: dict,
    producer: KafkaProducerManager,
) -> None:
    invoice_id = uuid.UUID(message_value["invoice_id"])
    tenant_id = uuid.UUID(message_value["tenant_id"])
    actor_id = uuid.UUID(message_value.get("uploaded_by", str(SYSTEM_ACTOR_ID)))

    async with async_session_factory() as session:
        result = await session.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == tenant_id,
            )
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            logger.warning("invoice_not_found", invoice_id=str(invoice_id))
            return

        old_status = invoice.status.value
        invoice.status = InvoiceStatus.EXTRACTING
        await log_audit_event(
            session,
            tenant_id=tenant_id,
            entity_type="invoice",
            entity_id=invoice_id,
            action="extraction_started",
            actor_id=actor_id,
            actor_role="system",
            old_value={"status": old_status},
            new_value={"status": InvoiceStatus.EXTRACTING.value},
        )
        await session.commit()

        try:
            extracted_data, confidence = await extract_invoice(message_value)
            invoice.status = InvoiceStatus.MATCHED
            invoice.invoice_number = extracted_data.get(
                "invoice_number", invoice.invoice_number
            )
            if extracted_data.get("amount") is not None:
                invoice.amount = Decimal(str(extracted_data["amount"]))
            if extracted_data.get("due_date"):
                invoice.due_date = date.fromisoformat(extracted_data["due_date"])
            invoice.line_items = extracted_data.get("line_items", [])
            invoice.extracted_data = extracted_data
            invoice.extraction_confidence = confidence

            await producer.send(
                TOPIC_INVOICE_EXTRACTED,
                {
                    "invoice_id": str(invoice_id),
                    "tenant_id": str(tenant_id),
                    "extracted_data": extracted_data,
                    "confidence_score": confidence,
                    "status": invoice.status.value,
                },
                key=str(invoice_id),
            )

            await log_audit_event(
                session,
                tenant_id=tenant_id,
                entity_type="invoice",
                entity_id=invoice_id,
                action="extraction_completed",
                actor_id=SYSTEM_ACTOR_ID,
                actor_role="system",
                new_value={
                    "status": invoice.status.value,
                    "confidence": confidence,
                    "extracted_data": extracted_data,
                },
            )
            logger.info(
                "invoice_extraction_completed",
                invoice_id=str(invoice_id),
                confidence=confidence,
            )
        except ExtractionError as exc:
            invoice.status = InvoiceStatus.REVIEW_REQUIRED
            invoice.flags = {**invoice.flags, "extraction_error": str(exc)}
            await log_audit_event(
                session,
                tenant_id=tenant_id,
                entity_type="invoice",
                entity_id=invoice_id,
                action="extraction_failed",
                actor_id=SYSTEM_ACTOR_ID,
                actor_role="system",
                reason=str(exc),
                new_value={"status": InvoiceStatus.REVIEW_REQUIRED.value},
            )
            logger.warning(
                "invoice_extraction_failed",
                invoice_id=str(invoice_id),
                error=str(exc),
            )
        except Exception:
            invoice.status = InvoiceStatus.REVIEW_REQUIRED
            invoice.flags = {**invoice.flags, "extraction_error": "unexpected_error"}
            await log_audit_event(
                session,
                tenant_id=tenant_id,
                entity_type="invoice",
                entity_id=invoice_id,
                action="extraction_failed",
                actor_id=SYSTEM_ACTOR_ID,
                actor_role="system",
                reason="Unexpected extraction error",
                new_value={"status": InvoiceStatus.REVIEW_REQUIRED.value},
            )
            logger.exception("invoice_extraction_unexpected_error", invoice_id=str(invoice_id))

        await session.commit()


async def run_invoice_worker() -> None:
    settings = get_settings()
    producer = KafkaProducerManager()
    await producer.start()

    consumer = AIOKafkaConsumer(
        TOPIC_INVOICE_RECEIVED,
        bootstrap_servers=settings.kafka_brokers,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    await consumer.start()
    logger.info(
        "invoice_worker_started",
        topic=TOPIC_INVOICE_RECEIVED,
        group=CONSUMER_GROUP,
    )

    try:
        async for message in consumer:
            try:
                await process_invoice_received(message.value, producer)
            except Exception:
                logger.exception(
                    "invoice_message_processing_failed",
                    offset=message.offset,
                    partition=message.partition,
                )
    finally:
        await consumer.stop()
        await producer.stop()
        logger.info("invoice_worker_stopped")


def main() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )
    asyncio.run(run_invoice_worker())


if __name__ == "__main__":
    main()
