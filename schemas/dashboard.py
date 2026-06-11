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


class MatchRateResponse(BaseModel):
    data_points: list[MatchRateDataPoint]
