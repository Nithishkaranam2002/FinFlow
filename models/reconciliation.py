import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from models.invoice import Invoice
    from models.payment import Payment


class MatchType(str, enum.Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    LLM_JUDGMENT = "llm_judgment"
    MANUAL = "manual"
    UNMATCHED = "unmatched"


class ReconciliationMatch(Base):
    __tablename__ = "reconciliation_matches"
    __table_args__ = (
        Index("ix_reconciliation_matches_tenant_id", "tenant_id"),
        Index("ix_reconciliation_matches_tenant_id_match_type", "tenant_id", "match_type"),
        Index("ix_reconciliation_matches_invoice_id", "invoice_id"),
        Index("ix_reconciliation_matches_payment_id", "payment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    bank_line_id: Mapped[str] = mapped_column(String(128), nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id")
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id")
    )
    match_type: Mapped[MatchType] = mapped_column(
        Enum(MatchType, name="match_type"),
        default=MatchType.UNMATCHED,
        nullable=False,
    )
    confidence_score: Mapped[float | None] = mapped_column(Float)
    llm_reasoning: Mapped[str | None] = mapped_column(Text)
    matched_by: Mapped[str | None] = mapped_column(String(128))
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    invoice: Mapped["Invoice | None"] = relationship(
        "Invoice", back_populates="reconciliation_matches"
    )
    payment: Mapped["Payment | None"] = relationship(
        "Payment", back_populates="reconciliation_matches"
    )
