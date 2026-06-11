import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from models.payment import Payment
    from models.reconciliation import ReconciliationMatch
    from models.vendor import Vendor


class InvoiceStatus(str, enum.Enum):
    RECEIVED = "received"
    EXTRACTING = "extracting"
    REVIEW_REQUIRED = "review_required"
    MATCHED = "matched"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_tenant_id", "tenant_id"),
        Index("ix_invoices_tenant_id_status", "tenant_id", "status"),
        Index("ix_invoices_vendor_id", "vendor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status"),
        default=InvoiceStatus.RECEIVED,
        nullable=False,
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    extracted_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    flags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="invoices")
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="invoice", lazy="selectin"
    )
    reconciliation_matches: Mapped[list["ReconciliationMatch"]] = relationship(
        "ReconciliationMatch", back_populates="invoice", lazy="selectin"
    )
