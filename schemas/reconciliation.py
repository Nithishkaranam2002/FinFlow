import uuid
from datetime import datetime

from pydantic import BaseModel

from models.reconciliation import MatchType


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
