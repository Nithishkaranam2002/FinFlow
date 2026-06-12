import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from models.reconciliation import MatchType, StatementStatus


class BankStatementLineCreate(BaseModel):
    statement_date: date | None = None
    transaction_date: date
    description: str = Field(min_length=1)
    amount: Decimal
    reference: str | None = None
    bank_transaction_id: str | None = None
    currency: str = "USD"


class BankStatementUploadResponse(BaseModel):
    statement_id: uuid.UUID
    line_count: int
    status: StatementStatus


class ReconciliationStatusResponse(BaseModel):
    statement_id: uuid.UUID
    status: StatementStatus
    total_lines: int
    matched_lines: int
    pending_lines: int
    unmatched_lines: int
    match_rate: float
    exact_matched: int
    fuzzy_matched: int
    llm_matched: int
    manual_matched: int


class ReconciliationExceptionItem(BaseModel):
    line_id: uuid.UUID
    transaction_date: date
    description: str
    amount: Decimal
    currency: str
    reference: str | None
    llm_explanation: str | None
    exception_reason: str | None
    suggested_action: str | None = None


class ReconciliationExceptionListResponse(BaseModel):
    items: list[ReconciliationExceptionItem]
    total: int
    page: int
    page_size: int


class ManualMatchRequest(BaseModel):
    invoice_id: uuid.UUID
    payment_id: uuid.UUID | None = None
    notes: str | None = None


class ReconciliationReportLine(BaseModel):
    line_id: uuid.UUID
    transaction_date: date
    description: str
    amount: Decimal
    currency: str
    match_type: MatchType | None
    confidence_score: float | None
    invoice_id: uuid.UUID | None
    payment_id: uuid.UUID | None
    llm_reasoning: str | None
    exception_reason: str | None


class ReconciliationReportResponse(BaseModel):
    statement_id: uuid.UUID
    filename: str
    status: StatementStatus
    generated_at: datetime
    summary: dict[str, Any]
    lines: list[ReconciliationReportLine]
    unmatched_explanations: list[str]


class ReconciliationMatchResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    bank_line_id: str
    invoice_id: uuid.UUID | None
    payment_id: uuid.UUID | None
    match_type: MatchType
    confidence_score: float | None
    llm_reasoning: str | None
    matched_by: str | None
    matched_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReconciliationListResponse(BaseModel):
    items: list[ReconciliationMatchResponse]
    total: int
