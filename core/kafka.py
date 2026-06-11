import json
from typing import Annotated, Any

import structlog
from aiokafka import AIOKafkaProducer
from fastapi import Depends, HTTPException, status
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import get_settings

logger = structlog.get_logger(__name__)

TOPIC_INVOICE_RECEIVED = "invoice.received"
TOPIC_INVOICE_EXTRACTED = "invoice.extracted"
TOPIC_INVOICE_MATCHED = "invoice.matched"
TOPIC_INVOICE_APPROVED = "invoice.approved"
TOPIC_PAYMENT_SCHEDULED = "payment.scheduled"
TOPIC_PAYMENT_CLEARED = "payment.cleared"
TOPIC_RECONCILIATION_STARTED = "reconciliation.started"
TOPIC_RECONCILIATION_COMPLETED = "reconciliation.completed"

ALL_TOPICS = [
    TOPIC_INVOICE_RECEIVED,
    TOPIC_INVOICE_EXTRACTED,
    TOPIC_INVOICE_MATCHED,
    TOPIC_INVOICE_APPROVED,
    TOPIC_PAYMENT_SCHEDULED,
    TOPIC_PAYMENT_CLEARED,
    TOPIC_RECONCILIATION_STARTED,
    TOPIC_RECONCILIATION_COMPLETED,
]


class KafkaProducerManager:
    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    @property
    def is_started(self) -> bool:
        return self._producer is not None

    async def start(self) -> None:
        if self._producer is not None:
            return

        settings = get_settings()
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_brokers,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            key_serializer=lambda key: key.encode("utf-8") if key is not None else None,
        )
        await self._producer.start()
        logger.info("kafka_producer_started", brokers=settings.kafka_brokers)

    async def stop(self) -> None:
        if self._producer is None:
            return
        await self._producer.stop()
        self._producer = None
        logger.info("kafka_producer_stopped")

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def _send_with_retry(
        self,
        topic: str,
        key: str | None,
        value: dict[str, Any],
    ) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka producer is not started")
        await self._producer.send_and_wait(topic, value=value, key=key)

    async def send(
        self,
        topic: str,
        value: dict[str, Any],
        key: str | None = None,
    ) -> None:
        try:
            await self._send_with_retry(topic, key, value)
            logger.info("kafka_message_sent", topic=topic, key=key)
        except Exception:
            logger.exception("kafka_message_send_failed", topic=topic, key=key)
            raise


kafka_producer_manager = KafkaProducerManager()


def get_producer() -> KafkaProducerManager:
    if not kafka_producer_manager.is_started:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka producer is not available",
        )
    return kafka_producer_manager


ProducerDep = Annotated[KafkaProducerManager, Depends(get_producer)]


async def publish_event(
    topic: str,
    payload: dict[str, Any],
    key: str | None = None,
) -> None:
    """Backward-compatible helper used by existing routes."""
    await kafka_producer_manager.send(topic, payload, key=key)
