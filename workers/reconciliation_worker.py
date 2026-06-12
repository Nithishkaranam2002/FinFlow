#!/usr/bin/env python3
"""Kafka consumer worker for reconciliation.started events."""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog
from aiokafka import AIOKafkaConsumer

from agents.reconciliation_agent import run_reconciliation_pipeline
from core.config import get_settings
from core.kafka import (
    TOPIC_RECONCILIATION_COMPLETED,
    TOPIC_RECONCILIATION_STARTED,
    KafkaProducerManager,
)
from core.tenant import set_current_tenant_id

logger = structlog.get_logger(__name__)

CONSUMER_GROUP = "finflow-reconciliation-workers"


async def process_reconciliation_started(
    message_value: dict,
    producer: KafkaProducerManager,
) -> None:
    bank_statement_id = message_value.get("bank_statement_id")
    tenant_id = message_value.get("tenant_id")

    if not bank_statement_id or not tenant_id:
        logger.warning("reconciliation_message_missing_fields", payload=message_value)
        return

    set_current_tenant_id(uuid.UUID(str(tenant_id)))
    logger.info(
        "reconciliation_started_received",
        bank_statement_id=bank_statement_id,
        tenant_id=tenant_id,
    )

    try:
        result = await run_reconciliation_pipeline(
            statement_id=str(bank_statement_id),
            tenant_id=str(tenant_id),
        )
    except Exception:
        logger.exception(
            "reconciliation_pipeline_failed",
            bank_statement_id=bank_statement_id,
            tenant_id=tenant_id,
        )
        raise

    report = result.get("report") or {}
    completion = {
        "bank_statement_id": bank_statement_id,
        "tenant_id": tenant_id,
        "reconciliation_id": str(uuid.uuid4()),
        "match_rate": report.get("match_rate", 0.0),
        "total_lines": report.get("total_lines", message_value.get("total_lines", 0)),
        "matched_lines": report.get("matched_lines", 0),
        "unmatched_lines": report.get("unmatched_lines", 0),
        "status": "completed",
        "engine": "reconciliation-agent-v1",
        "summary": report,
    }

    await producer.send(
        TOPIC_RECONCILIATION_COMPLETED,
        completion,
        key=str(bank_statement_id),
    )
    logger.info(
        "reconciliation_completed_published",
        bank_statement_id=bank_statement_id,
        match_rate=completion["match_rate"],
    )


async def run_reconciliation_worker() -> None:
    settings = get_settings()
    producer = KafkaProducerManager()
    await producer.start()

    consumer = AIOKafkaConsumer(
        TOPIC_RECONCILIATION_STARTED,
        bootstrap_servers=settings.kafka_brokers,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    await consumer.start()
    logger.info(
        "reconciliation_worker_started",
        topic=TOPIC_RECONCILIATION_STARTED,
        group=CONSUMER_GROUP,
    )

    try:
        async for message in consumer:
            try:
                await process_reconciliation_started(message.value, producer)
            except Exception:
                logger.exception(
                    "reconciliation_message_processing_failed",
                    offset=message.offset,
                    partition=message.partition,
                )
    finally:
        await consumer.stop()
        await producer.stop()
        logger.info("reconciliation_worker_stopped")


def main() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )
    asyncio.run(run_reconciliation_worker())


if __name__ == "__main__":
    main()
