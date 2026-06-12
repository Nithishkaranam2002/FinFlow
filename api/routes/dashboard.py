from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import and_, case, func, select

from api.deps import ApClerkUser, DbSession
from models.invoice import Invoice, InvoiceStatus
from models.reconciliation import MatchType, ReconciliationMatch
from schemas.dashboard import (
    DashboardStatsResponse,
    LLMCostByAgent,
    LLMCostByDay,
    LLMCostByModel,
    LLMCostSummaryResponse,
    MatchRateDataPoint,
    MatchRateResponse,
    StatusCount,
)
from core.llm_gateway import CostTracker

router = APIRouter(tags=["dashboard"])

EXCEPTION_STATUSES = {
    InvoiceStatus.REVIEW_REQUIRED,
    InvoiceStatus.REJECTED,
}


def _status_counts(rows: list[tuple[InvoiceStatus, int]]) -> list[StatusCount]:
    return [StatusCount(status=status, count=count) for status, count in rows]


async def _counts_by_status(
    db: DbSession,
    tenant_id,
    start: datetime,
    end: datetime,
) -> list[StatusCount]:
    result = await db.execute(
        select(Invoice.status, func.count())
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.created_at >= start,
            Invoice.created_at < end,
        )
        .group_by(Invoice.status)
    )
    return _status_counts(list(result.all()))


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    db: DbSession,
    current_user: ApClerkUser,
) -> DashboardStatsResponse:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)

    invoices_today = await _counts_by_status(
        db, current_user.tenant_id, today_start, today_start + timedelta(days=1)
    )
    invoices_this_week = await _counts_by_status(
        db, current_user.tenant_id, week_start, now + timedelta(days=1)
    )
    invoices_this_month = await _counts_by_status(
        db, current_user.tenant_id, month_start, now + timedelta(days=1)
    )

    processing_result = await db.execute(
        select(
            func.avg(
                func.extract(
                    "epoch",
                    Invoice.updated_at - Invoice.created_at,
                )
            )
        ).where(
            Invoice.tenant_id == current_user.tenant_id,
            Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.PAID]),
        )
    )
    avg_seconds = processing_result.scalar_one() or 0.0
    average_processing_time_hours = round(float(avg_seconds) / 3600, 2)

    totals_result = await db.execute(
        select(
            func.count(),
            func.sum(
                case((Invoice.status.in_(list(EXCEPTION_STATUSES)), 1), else_=0)
            ),
        ).where(Invoice.tenant_id == current_user.tenant_id)
    )
    total_invoices, exception_count = totals_result.one()
    exception_rate = round(
        (int(exception_count or 0) / total_invoices * 100) if total_invoices else 0.0,
        2,
    )

    # Placeholder cost model: $0.12 per invoice processed this month.
    month_count_result = await db.execute(
        select(func.count()).where(
            Invoice.tenant_id == current_user.tenant_id,
            Invoice.created_at >= month_start,
        )
    )
    month_count = month_count_result.scalar_one()
    cost_tracker = CostTracker()
    month_start_date = month_start.date()
    today = date.today()
    cost_summary = await cost_tracker.get_cost_summary(
        current_user.tenant_id,
        (month_start_date, today),
    )
    cost_per_invoice_usd = cost_summary["average_cost_per_invoice_usd"]

    return DashboardStatsResponse(
        invoices_today=invoices_today,
        invoices_this_week=invoices_this_week,
        invoices_this_month=invoices_this_month,
        average_processing_time_hours=average_processing_time_hours,
        exception_rate=exception_rate,
        cost_per_invoice_usd=cost_per_invoice_usd if month_count else 0.0,
    )


@router.get("/match-rate", response_model=MatchRateResponse)
async def get_match_rate(
    db: DbSession,
    current_user: ApClerkUser,
) -> MatchRateResponse:
    start_date = date.today() - timedelta(days=29)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)

    result = await db.execute(
        select(
            func.date(ReconciliationMatch.created_at).label("day"),
            func.count().label("total_lines"),
            func.sum(
                case(
                    (ReconciliationMatch.match_type != MatchType.UNMATCHED, 1),
                    else_=0,
                )
            ).label("matched_lines"),
        )
        .where(
            ReconciliationMatch.tenant_id == current_user.tenant_id,
            ReconciliationMatch.created_at >= start_dt,
        )
        .group_by(func.date(ReconciliationMatch.created_at))
        .order_by(func.date(ReconciliationMatch.created_at))
    )

    data_points: list[MatchRateDataPoint] = []
    for row in result.all():
        total_lines = int(row.total_lines or 0)
        matched_lines = int(row.matched_lines or 0)
        match_rate = round((matched_lines / total_lines * 100) if total_lines else 0.0, 2)
        data_points.append(
            MatchRateDataPoint(
                date=row.day,
                total_lines=total_lines,
                matched_lines=matched_lines,
                match_rate=match_rate,
            )
        )

    return MatchRateResponse(data_points=data_points)


@router.get("/llm-costs", response_model=LLMCostSummaryResponse)
async def get_llm_costs(
    current_user: ApClerkUser,
) -> LLMCostSummaryResponse:
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    summary = await CostTracker().get_cost_summary(
        current_user.tenant_id,
        (start_date, end_date),
    )
    return LLMCostSummaryResponse(
        total_cost_usd=summary["total_cost_usd"],
        total_calls=summary["total_calls"],
        total_input_tokens=summary["total_input_tokens"],
        total_output_tokens=summary["total_output_tokens"],
        average_cost_per_invoice_usd=summary["average_cost_per_invoice_usd"],
        invoice_count=summary["invoice_count"],
        cost_by_day=[
            LLMCostByDay(
                date=date.fromisoformat(item["date"]),
                cost_usd=item["cost_usd"],
                calls=item["calls"],
            )
            for item in summary["cost_by_day"]
        ],
        cost_by_model=[LLMCostByModel(**item) for item in summary["cost_by_model"]],
        cost_by_agent=[LLMCostByAgent(**item) for item in summary["cost_by_agent"]],
    )
