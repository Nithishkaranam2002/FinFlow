#!/usr/bin/env python3
"""Kafka consumer worker for reconciliation.started events."""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog
from aiokafka import AIOKafkaConsumer

from core.config import get_settings
from core.kafka import (
    TOPIC_RECONCILIATION_COMPLETED,
    TOPIC_RECONCILIATION_STARTED,
    KafkaProducerManager,
)

logger = structlog.get_logger(__name__)

CONSUMER_GROUP = "finflow-reconciliation-workers"
MOCK_MATCH_RATE = 0.85


async def process_reconciliation_started(
    message_value: dict,
    producer: KafkaProducerManager,
) -> None:
    bank_statement_id = message_value.get("bank_statement_id")
    tenant_id = message_value.get("tenant_id")

    logger.info(
        "reconciliation_started_received",
        bank_statement_id=bank_statement_id,
        tenant_id=tenant_id,
    )

    total_lines = int(message_value.get("total_lines", 100))
    matched_lines = int(total_lines * MOCK_MATCH_RATE)

    result = {
        "bank_statement_id": bank_statement_id,
        "tenant_id": tenant_id,
        "reconciliation_id": str(uuid.uuid4()),
        "match_rate": MOCK_MATCH_RATE,
        "total_lines": total_lines,
        "matched_lines": matched_lines,
        "unmatched_lines": total_lines - matched_lines,
        "status": "completed",
        "engine": "stub-v1",
    }

    await producer.send(
        TOPIC_RECONCILIATION_COMPLETED,
        result,
        key=str(bank_statement_id) if bank_statement_id else None,
    )
    logger.info(
        "reconciliation_completed_published",
        bank_statement_id=bank_statement_id,
        match_rate=MOCK_MATCH_RATE,
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
