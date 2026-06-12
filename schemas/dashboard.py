from datetime import date

from pydantic import BaseModel

from models.invoice import InvoiceStatus


class StatusCount(BaseModel):
    status: InvoiceStatus
    count: int


class DashboardStatsResponse(BaseModel):
    invoices_today: list[StatusCount]
    invoices_this_week: list[StatusCount]
    invoices_this_month: list[StatusCount]
    average_processing_time_hours: float
    exception_rate: float
    cost_per_invoice_usd: float


class MatchRateDataPoint(BaseModel):
    date: date
    total_lines: int
    matched_lines: int
    match_rate: float


class LLMCostByDay(BaseModel):
    date: date
    cost_usd: float
    calls: int


class LLMCostByModel(BaseModel):
    model: str
    cost_usd: float
    calls: int


class LLMCostByAgent(BaseModel):
    agent: str
    cost_usd: float
    calls: int


class LLMCostSummaryResponse(BaseModel):
    total_cost_usd: float
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    average_cost_per_invoice_usd: float
    invoice_count: int
    cost_by_day: list[LLMCostByDay]
    cost_by_model: list[LLMCostByModel]
    cost_by_agent: list[LLMCostByAgent]


class MatchRateResponse(BaseModel):
    data_points: list[MatchRateDataPoint]
