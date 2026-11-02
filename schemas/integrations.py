import uuid
from datetime import datetime

from pydantic import BaseModel

from models.webhook_delivery import WebhookDelivery


class WebhookDeliveryResponse(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: str | None
    vendor_name: str | None
    event: str
    target_url: str
    status: str
    attempts: int
    last_status_code: int | None
    last_error: str | None
    created_at: datetime
    last_attempt_at: datetime | None
    next_retry_at: datetime | None
    sent_at: datetime | None

    @classmethod
    def from_model(cls, delivery: WebhookDelivery) -> "WebhookDeliveryResponse":
        payload = delivery.payload or {}
        return cls(
            id=delivery.id,
            invoice_id=delivery.invoice_id,
            invoice_number=payload.get("invoice_number"),
            vendor_name=(payload.get("vendor") or {}).get("name"),
            event=delivery.event,
            target_url=delivery.target_url,
            status=delivery.status,
            attempts=delivery.attempts,
            last_status_code=delivery.last_status_code,
            last_error=delivery.last_error,
            created_at=delivery.created_at,
            last_attempt_at=delivery.last_attempt_at,
            next_retry_at=delivery.next_retry_at,
            sent_at=delivery.sent_at,
        )


class WebhookSummaryResponse(BaseModel):
    configured: bool
    target_url: str | None
    last_status: str | None
    last_delivery_at: datetime | None
    last_error: str | None
    next_retry_at: datetime | None
    last_success_at: datetime | None
    failures_24h: int
