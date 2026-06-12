import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from models.invoice import InvoiceStatus

T = TypeVar("T")


class LineItem(BaseModel):
    description: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    total: Decimal = Field(ge=0)


class ExtractedInvoiceData(BaseModel):
    invoice_number: str = Field(min_length=1)
    vendor_name: str = Field(min_length=1)
    vendor_email: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal = Field(gt=0)
    currency: str = "USD"
    line_items: list[LineItem] = Field(default_factory=list)
    payment_terms: str | None = None
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ConfidentValue(BaseModel, Generic[T]):
    value: T | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class ConfidentLineItem(BaseModel):
    description: ConfidentValue[str]
    quantity: ConfidentValue[Decimal]
    unit_price: ConfidentValue[Decimal]
    total: ConfidentValue[Decimal]


class ExtractedInvoiceDataWithConfidence(BaseModel):
    invoice_number: ConfidentValue[str]
    vendor_name: ConfidentValue[str]
    vendor_email: ConfidentValue[str]
    invoice_date: ConfidentValue[date]
    due_date: ConfidentValue[date]
    subtotal: ConfidentValue[Decimal]
    tax_amount: ConfidentValue[Decimal]
    total_amount: ConfidentValue[Decimal]
    currency: ConfidentValue[str]
    line_items: ConfidentValue[list[LineItem]]
    payment_terms: ConfidentValue[str]
    notes: ConfidentValue[str]

    def to_extracted_data(self) -> ExtractedInvoiceData:
        return ExtractedInvoiceData(
            invoice_number=self.invoice_number.value or "UNKNOWN",
            vendor_name=self.vendor_name.value or "UNKNOWN",
            vendor_email=self.vendor_email.value,
            invoice_date=self.invoice_date.value,
            due_date=self.due_date.value,
            subtotal=self.subtotal.value,
            tax_amount=self.tax_amount.value,
            total_amount=self.total_amount.value or Decimal("0.01"),
            currency=self.currency.value or "USD",
            line_items=self.line_items.value or [],
            payment_terms=self.payment_terms.value,
            notes=self.notes.value,
        )

    def confidence_map(self) -> dict[str, float]:
        return {
            "invoice_number": self.invoice_number.confidence,
            "vendor_name": self.vendor_name.confidence,
            "vendor_email": self.vendor_email.confidence,
            "invoice_date": self.invoice_date.confidence,
            "due_date": self.due_date.confidence,
            "subtotal": self.subtotal.confidence,
            "tax_amount": self.tax_amount.confidence,
            "total_amount": self.total_amount.confidence,
            "currency": self.currency.confidence,
            "line_items": self.line_items.confidence,
            "payment_terms": self.payment_terms.confidence,
            "notes": self.notes.confidence,
        }


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    vendor_id: uuid.UUID
    invoice_number: str
    amount: Decimal
    currency: str
    due_date: date | None
    line_items: list[dict[str, Any]]
    status: InvoiceStatus
    extraction_confidence: float | None
    extracted_data: dict[str, Any] | None
    flags: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvoiceUploadResponse(BaseModel):
    invoice_id: uuid.UUID
    status: InvoiceStatus


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    total: int
    page: int
    page_size: int


class InvoiceRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class InvoiceApproveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class ExtractionCorrectionRequest(BaseModel):
    corrections: dict[str, Any] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=2000)


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor_id: uuid.UUID
    actor_role: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    reason: str | None
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
