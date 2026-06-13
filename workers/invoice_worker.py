#!/usr/bin/env python3
"""Kafka consumer worker for invoice.received events."""

from __future__ import annotations

import asyncio
import json
import uuid

from datetime import datetime, timedelta, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import select

from core.config import get_settings
from core.database import async_session_factory
from core.kafka import TOPIC_INVOICE_RECEIVED, TOPIC_INVOICE_RECEIVED_DLQ
from models.invoice import Invoice, InvoiceStatus
from services.audit import log_audit_event
from services.invoice_pipeline import build_state_from_kafka_payload, run_invoice_pipeline

logger = structlog.get_logger(__name__)

CONSUMER_GROUP = "finflow-invoice-workers"
SYSTEM_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SKIP_STATUSES = {
    InvoiceStatus.MATCHED,
    InvoiceStatus.PENDING_APPROVAL,
    InvoiceStatus.APPROVED,
    InvoiceStatus.REJECTED,
    InvoiceStatus.PAID,
    InvoiceStatus.REVIEW_REQUIRED,
}


def _should_skip_invoice(invoice: Invoice, is_recovery: bool) -> bool:
    if invoice.status in SKIP_STATUSES:
        return True
    if invoice.status == InvoiceStatus.EXTRACTING and not is_recovery:
        updated_at = invoice.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - updated_at < timedelta(minutes=5):
            return True
    return False


async def publish_invoice_dlq(payload: dict, error: str, producer: AIOKafkaProducer) -> None:
    await producer.send_and_wait(
        TOPIC_INVOICE_RECEIVED_DLQ,
        value={
            **payload,
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        },
        key=payload.get("invoice_id"),
    )


async def process_invoice_received(message_value: dict) -> None:
    invoice_id = uuid.UUID(message_value["invoice_id"])
    tenant_id = uuid.UUID(message_value["tenant_id"])
    actor_id = uuid.UUID(message_value.get("uploaded_by", str(SYSTEM_ACTOR_ID)))
    is_recovery = bool(message_value.get("recovery"))

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

        if _should_skip_invoice(invoice, is_recovery):
            logger.info(
                "invoice_processing_skipped",
                invoice_id=str(invoice_id),
                status=invoice.status.value,
                recovery=is_recovery,
            )
            return

        old_status = invoice.status.value
        invoice.status = InvoiceStatus.EXTRACTING
        await log_audit_event(
            session,
            tenant_id=tenant_id,
            entity_type="invoice",
            entity_id=invoice_id,
            action="pipeline_started",
            actor_id=actor_id,
            actor_role="system",
            old_value={"status": old_status},
            new_value={"status": InvoiceStatus.EXTRACTING.value},
        )
        await session.commit()

    try:
        state = build_state_from_kafka_payload(message_value)
        result = await run_invoice_pipeline(state)
    except Exception:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Invoice).where(
                    Invoice.id == invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
            )
            invoice = result.scalar_one_or_none()
            if invoice and invoice.status == InvoiceStatus.EXTRACTING:
                invoice.status = InvoiceStatus.REVIEW_REQUIRED
                invoice.flags = {
                    **(invoice.flags or {}),
                    "pipeline_error": "unexpected_error",
                }
            await log_audit_event(
                session,
                tenant_id=tenant_id,
                entity_type="invoice",
                entity_id=invoice_id,
                action="pipeline_failed",
                actor_id=SYSTEM_ACTOR_ID,
                actor_role="system",
                reason="Unexpected pipeline error",
                new_value={"status": InvoiceStatus.REVIEW_REQUIRED.value},
            )
            await session.commit()
        logger.exception("invoice_pipeline_failed", invoice_id=str(invoice_id))
        return

    async with async_session_factory() as session:
        refreshed = await session.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == tenant_id,
            )
        )
        invoice = refreshed.scalar_one()
        await log_audit_event(
            session,
            tenant_id=tenant_id,
            entity_type="invoice",
            entity_id=invoice_id,
            action="pipeline_completed",
            actor_id=SYSTEM_ACTOR_ID,
            actor_role="system",
            new_value={
                "status": invoice.status.value,
                "approval_status": result.get("approval_status"),
                "steps": result.get("step_history"),
            },
        )
        await session.commit()

    logger.info(
        "invoice_pipeline_finished",
        invoice_id=str(invoice_id),
        status=invoice.status.value,
        approval_status=result.get("approval_status"),
    )


async def run_invoice_worker() -> None:
    settings = get_settings()
    try:
        from core.checkpointer import init_checkpointer
        from agents.graph import reset_invoice_graph

        await init_checkpointer()
        reset_invoice_graph()
    except Exception:
        logger.exception("invoice_worker_checkpointer_init_failed")
        if settings.is_production:
            raise

    consumer = AIOKafkaConsumer(
        TOPIC_INVOICE_RECEIVED,
        bootstrap_servers=settings.kafka_brokers,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    dlq_producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_brokers,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        key_serializer=lambda key: key.encode("utf-8") if key is not None else None,
    )
    await consumer.start()
    await dlq_producer.start()
    logger.info(
        "invoice_worker_started",
        topic=TOPIC_INVOICE_RECEIVED,
        group=CONSUMER_GROUP,
    )

    try:
        async for message in consumer:
            try:
                await process_invoice_received(message.value)
                await consumer.commit()
            except Exception as exc:
                logger.exception(
                    "invoice_message_processing_failed",
                    offset=message.offset,
                    partition=message.partition,
                )
                try:
                    await publish_invoice_dlq(message.value, str(exc), dlq_producer)
                except Exception:
                    logger.exception("invoice_dlq_publish_failed", offset=message.offset)
                await consumer.commit()
    finally:
        await dlq_producer.stop()
        await consumer.stop()
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
