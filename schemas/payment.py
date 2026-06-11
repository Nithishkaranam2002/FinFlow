import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from models.payment import PaymentStatus


class PaymentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    invoice_id: uuid.UUID
    amount: Decimal
    status: PaymentStatus
    payment_reference: str | None
    bank_transaction_id: str | None
    scheduled_at: datetime | None
    sent_at: datetime | None
    cleared_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int
