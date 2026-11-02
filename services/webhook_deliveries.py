"""Persisted outbound webhook deliveries: send, record, retry with backoff, report."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select

from core.database import async_session_factory
from models.webhook_delivery import (
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_SENT,
    WebhookDelivery,
)

logger = structlog.get_logger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 3.0
# Automatic retries after the first attempt fails: 4 attempts at most.
RETRY_DELAYS_SECONDS: tuple[float, ...] = (10, 30, 90)


class DeliveryNotFoundError(Exception):
    pass


class DeliveryAlreadySentError(Exception):
    pass


def idempotency_key(invoice_id: str, event: str) -> str:
    return f"{invoice_id}:{event}"


def describe_delivery_error(
    *, exc: BaseException | None = None, status_code: int | None = None
) -> str:
    """Plain-English explanation of why a delivery failed."""
    if status_code is not None:
        if status_code == 404:
            return (
                "The receiver returned 404 Not Found. The webhook URL may be wrong "
                "or the workflow is not active."
            )
        if status_code in (401, 403):
            return f"The receiver refused the request (HTTP {status_code}). Check its authentication settings."
        if status_code >= 500:
            return f"The receiver had an internal error (HTTP {status_code})."
        return f"The receiver rejected the request (HTTP {status_code})."
    if isinstance(exc, httpx.TimeoutException):
        return f"The receiver did not answer within {WEBHOOK_TIMEOUT_SECONDS:.0f} seconds."
    if isinstance(exc, httpx.ConnectError):
        return "Could not connect to the receiver. Is it running and reachable?"
    if exc is not None:
        return f"Unexpected error while sending: {exc.__class__.__name__}."
    return "Unknown error."


async def run_with_retries(
    attempt: Callable[[float | None], Awaitable[bool]],
    delays: Sequence[float] = RETRY_DELAYS_SECONDS,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> bool:
    """Call attempt(next_delay) until it succeeds or the retry schedule is used up.

    next_delay is the wait before the following retry, or None on the final attempt.
    An attempt that raises counts as a failure.
    """
    for index in range(len(delays) + 1):
        next_delay = delays[index] if index < len(delays) else None
        try:
            succeeded = await attempt(next_delay)
        except Exception:
            logger.exception("webhook_attempt_crashed")
            succeeded = False
        if succeeded:
            return True
        if next_delay is None:
            return False
        await sleep(next_delay)
    return False


async def create_delivery(
    *, tenant_id: str, invoice_id: str, event: str, target_url: str, payload: dict[str, Any]
) -> uuid.UUID:
    async with async_session_factory() as db:
        delivery = WebhookDelivery(
            tenant_id=uuid.UUID(tenant_id),
            invoice_id=uuid.UUID(invoice_id),
            event=event,
            target_url=target_url,
            payload=payload,
            status=DELIVERY_PENDING,
            attempts=0,
        )
        db.add(delivery)
        await db.commit()
        return delivery.id


async def attempt_delivery(delivery_id: uuid.UUID, next_retry_in: float | None = None) -> bool:
    """Send one delivery once and record the outcome. Never raises; returns True when sent."""
    async with async_session_factory() as db:
        delivery = await db.get(WebhookDelivery, delivery_id)
        if delivery is None:
            return True
        if delivery.status == DELIVERY_SENT:
            return True

        now = datetime.now(timezone.utc)
        status_code: int | None = None
        error: str | None = None
        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    delivery.target_url,
                    json=delivery.payload,
                    headers={
                        "Idempotency-Key": idempotency_key(str(delivery.invoice_id), delivery.event),
                        "X-FinFlow-Delivery-Id": str(delivery.id),
                    },
                )
            status_code = response.status_code
            if response.is_error:
                error = describe_delivery_error(status_code=status_code)
        except Exception as exc:
            error = describe_delivery_error(exc=exc)
            logger.warning(
                "approval_webhook_failed",
                delivery_id=str(delivery_id),
                invoice_id=str(delivery.invoice_id),
                error=repr(exc),
            )

        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.last_status_code = status_code
        if error is None:
            delivery.status = DELIVERY_SENT
            delivery.sent_at = now
            delivery.last_error = None
            delivery.next_retry_at = None
            logger.info(
                "approval_webhook_sent",
                delivery_id=str(delivery_id),
                invoice_id=str(delivery.invoice_id),
                attempts=delivery.attempts,
                status_code=status_code,
                response=response.text[:500],
            )
        else:
            delivery.status = DELIVERY_FAILED
            delivery.last_error = error
            delivery.next_retry_at = (
                now + timedelta(seconds=next_retry_in) if next_retry_in is not None else None
            )
            if status_code is not None:
                logger.warning(
                    "approval_webhook_failed",
                    delivery_id=str(delivery_id),
                    invoice_id=str(delivery.invoice_id),
                    status_code=status_code,
                )
        await db.commit()
        return error is None


async def deliver_with_retries(delivery_id: uuid.UUID) -> bool:
    return await run_with_retries(lambda next_delay: attempt_delivery(delivery_id, next_delay))


async def retry_delivery_now(*, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> WebhookDelivery:
    """Manual retry from the Integrations page: one attempt, right away."""
    async with async_session_factory() as db:
        delivery = await db.get(WebhookDelivery, delivery_id)
        if delivery is None or delivery.tenant_id != tenant_id:
            raise DeliveryNotFoundError(str(delivery_id))
        if delivery.status == DELIVERY_SENT:
            raise DeliveryAlreadySentError(str(delivery_id))

    await attempt_delivery(delivery_id, next_retry_in=None)

    async with async_session_factory() as db:
        refreshed = await db.get(WebhookDelivery, delivery_id)
        assert refreshed is not None
        return refreshed


async def list_deliveries(*, tenant_id: uuid.UUID, limit: int = 50) -> list[WebhookDelivery]:
    async with async_session_factory() as db:
        result = await db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.tenant_id == tenant_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def delivery_summary(*, tenant_id: uuid.UUID) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    async with async_session_factory() as db:
        latest = (
            await db.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.tenant_id == tenant_id)
                .order_by(WebhookDelivery.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        last_success_at = (
            await db.execute(
                select(func.max(WebhookDelivery.sent_at)).where(
                    WebhookDelivery.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        failures_24h = (
            await db.execute(
                select(func.count())
                .select_from(WebhookDelivery)
                .where(
                    WebhookDelivery.tenant_id == tenant_id,
                    WebhookDelivery.status == DELIVERY_FAILED,
                    WebhookDelivery.created_at >= since,
                )
            )
        ).scalar_one()

    return {
        "last_status": latest.status if latest else None,
        "last_delivery_at": latest.created_at if latest else None,
        "last_error": latest.last_error if latest else None,
        "next_retry_at": latest.next_retry_at if latest else None,
        "last_success_at": last_success_at,
        "failures_24h": failures_24h,
    }
