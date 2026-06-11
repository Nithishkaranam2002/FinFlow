import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from schemas.invoice import InvoiceResponse
from schemas.payment import PaymentResponse


class VendorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    bank_account: str | None = Field(default=None, max_length=64)
    payment_terms_days: int = Field(default=30, ge=0, le=365)


class VendorResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    email: str | None
    bank_account: str | None
    bank_account_changed_at: datetime | None
    payment_terms_days: int
    total_invoices: int
    total_paid: Decimal
    risk_score: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VendorDetailResponse(VendorResponse):
    invoices: list[InvoiceResponse] = []
    payments: list[PaymentResponse] = []
