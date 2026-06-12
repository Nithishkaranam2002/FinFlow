import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.enums import pg_enum

if TYPE_CHECKING:
    from models.invoice import Invoice
    from models.payment import Payment


class MatchType(str, enum.Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    LLM_JUDGMENT = "llm_judgment"
    MANUAL = "manual"
    UNMATCHED = "unmatched"


class StatementStatus(str, enum.Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BankStatement(Base):
    __tablename__ = "bank_statements"
    __table_args__ = (
        Index("ix_bank_statements_tenant_id", "tenant_id"),
        Index("ix_bank_statements_tenant_id_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_format: Mapped[str] = mapped_column(String(32), nullable=False)
    statement_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[StatementStatus] = mapped_column(
        pg_enum(StatementStatus, "statement_status"),
        default=StatementStatus.PROCESSING,
        nullable=False,
    )
    line_count: Mapped[int] = mapped_column(default=0, nullable=False)
    report_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lines: Mapped[list["BankStatementLine"]] = relationship(
        "BankStatementLine", back_populates="statement", lazy="selectin"
    )


class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    __table_args__ = (
        Index("ix_bank_statement_lines_tenant_id", "tenant_id"),
        Index("ix_bank_statement_lines_statement_id", "statement_id"),
        Index("ix_bank_statement_lines_tenant_id_is_matched", "tenant_id", "is_matched"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_statements.id"), nullable=False
    )
    statement_date: Mapped[date | None] = mapped_column(Date)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(256))
    bank_transaction_id: Mapped[str | None] = mapped_column(String(128))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    is_matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exception_reason: Mapped[str | None] = mapped_column(Text)
    llm_explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    statement: Mapped["BankStatement"] = relationship(
        "BankStatement", back_populates="lines"
    )
    matches: Mapped[list["ReconciliationMatch"]] = relationship(
        "ReconciliationMatch",
        back_populates="bank_line",
        foreign_keys="ReconciliationMatch.bank_statement_line_id",
    )


class ReconciliationMatch(Base):
    __tablename__ = "reconciliation_matches"
    __table_args__ = (
        Index("ix_reconciliation_matches_tenant_id", "tenant_id"),
        Index("ix_reconciliation_matches_tenant_id_match_type", "tenant_id", "match_type"),
        Index("ix_reconciliation_matches_invoice_id", "invoice_id"),
        Index("ix_reconciliation_matches_payment_id", "payment_id"),
        Index("ix_reconciliation_matches_bank_line_id", "bank_line_id"),
        Index("ix_reconciliation_matches_statement_id", "statement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_statements.id")
    )
    bank_statement_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_statement_lines.id")
    )
    bank_line_id: Mapped[str] = mapped_column(String(128), nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id")
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id")
    )
    match_type: Mapped[MatchType] = mapped_column(
        pg_enum(MatchType, "match_type"),
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
    bank_line: Mapped["BankStatementLine | None"] = relationship(
        "BankStatementLine",
        back_populates="matches",
        foreign_keys="ReconciliationMatch.bank_statement_line_id",
    )
