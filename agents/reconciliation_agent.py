"""Three-pass bank reconciliation agent with LangGraph orchestration."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import structlog
from langgraph.graph import END, START, StateGraph
from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import BaseAgent
from agents.reconciliation_state import ReconciliationState, create_reconciliation_state
from core.config import get_settings
from core.database import async_session_factory
from core.observability import trace_agent_step
from core.tenant import set_current_tenant_id
from models.invoice import Invoice
from models.payment import Payment
from models.reconciliation import BankStatement, BankStatementLine, MatchType, ReconciliationMatch, StatementStatus
from models.user import User, UserRole
from services.reconciliation_vectors import index_tenant_payments, search_similar_payments
from services.statement_parser import clean_description

logger = structlog.get_logger(__name__)

class ReconciliationAgent(BaseAgent):
    agent_name = "reconciliation"


_agent = ReconciliationAgent()
EXACT_DATE_WINDOW_DAYS = 5
FUZZY_MATCH_THRESHOLD = 0.80
FUZZY_CANDIDATE_THRESHOLD = 0.65
LLM_MATCH_THRESHOLD = 70


def _payment_date(payment: Payment) -> datetime:
    return (
        payment.cleared_at
        or payment.sent_at
        or payment.scheduled_at
        or payment.created_at
    )


def _references_overlap(bank_ref: str | None, payment_ref: str | None) -> bool:
    if not bank_ref or not payment_ref:
        return False
    left = clean_description(bank_ref).upper()
    right = clean_description(payment_ref).upper()
    if len(left) < 3 or len(right) < 3:
        return left == right
    return left in right or right in left


def _amounts_equal(left: Decimal, right: Decimal) -> bool:
    return abs(left) == abs(right)


async def _get_unmatched_lines(
    db: AsyncSession,
    *,
    statement_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> list[BankStatementLine]:
    result = await db.execute(
        select(BankStatementLine)
        .where(
            BankStatementLine.statement_id == statement_id,
            BankStatementLine.tenant_id == tenant_id,
            BankStatementLine.is_matched.is_(False),
        )
        .order_by(BankStatementLine.transaction_date.asc())
    )
    return list(result.scalars().all())


async def _create_match(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    statement_id: uuid.UUID,
    line: BankStatementLine,
    payment: Payment | None,
    invoice_id: uuid.UUID | None,
    match_type: MatchType,
    confidence: float,
    llm_reasoning: str | None = None,
    matched_by: str = "system",
) -> ReconciliationMatch:
    line.is_matched = True
    match = ReconciliationMatch(
        tenant_id=tenant_id,
        statement_id=statement_id,
        bank_statement_line_id=line.id,
        bank_line_id=str(line.id),
        invoice_id=invoice_id or (payment.invoice_id if payment else None),
        payment_id=payment.id if payment else None,
        match_type=match_type,
        confidence_score=confidence,
        llm_reasoning=llm_reasoning,
        matched_by=matched_by,
        matched_at=datetime.now(timezone.utc),
    )
    db.add(match)
    await db.flush()
    return match


@trace_agent_step("reconciliation")
async def exact_match_node(state: ReconciliationState) -> dict:
    update = _agent.log_step(
        {"invoice_id": state["statement_id"], "tenant_id": state["tenant_id"]},
        "exact_match",
    )
    statement_id = uuid.UUID(state["statement_id"])
    tenant_id = uuid.UUID(state["tenant_id"])
    matched_count = 0

    async with async_session_factory() as db:
        set_current_tenant_id(tenant_id)
        lines = await _get_unmatched_lines(db, statement_id=statement_id, tenant_id=tenant_id)
        payments_result = await db.execute(
            select(Payment).where(Payment.tenant_id == tenant_id)
        )
        payments = list(payments_result.scalars().all())

        for line in lines:
            txn_date = line.transaction_date
            for payment in payments:
                payment_dt = _payment_date(payment).date()
                if abs((payment_dt - txn_date).days) > EXACT_DATE_WINDOW_DAYS:
                    continue
                if not _amounts_equal(line.amount, payment.amount):
                    continue
                if not _references_overlap(line.reference, payment.payment_reference):
                    if line.bank_transaction_id and payment.bank_transaction_id:
                        if not _references_overlap(line.bank_transaction_id, payment.bank_transaction_id):
                            continue
                    elif line.reference or payment.payment_reference:
                        continue

                await _create_match(
                    db,
                    tenant_id=tenant_id,
                    statement_id=statement_id,
                    line=line,
                    payment=payment,
                    invoice_id=payment.invoice_id,
                    match_type=MatchType.EXACT,
                    confidence=1.0,
                )
                matched_count += 1
                break

        await db.commit()

    logger.info("exact_match_complete", statement_id=state["statement_id"], matched=matched_count)
    return {**update, "exact_matched_count": matched_count}


@trace_agent_step("reconciliation")
async def fuzzy_match_node(state: ReconciliationState) -> dict:
    update = _agent.log_step(
        {"invoice_id": state["statement_id"], "tenant_id": state["tenant_id"]},
        "fuzzy_match",
    )
    statement_id = uuid.UUID(state["statement_id"])
    tenant_id = uuid.UUID(state["tenant_id"])
    matched_count = 0
    fuzzy_candidates: list[dict[str, Any]] = []

    async with async_session_factory() as db:
        set_current_tenant_id(tenant_id)
        await index_tenant_payments(db, tenant_id)
        lines = await _get_unmatched_lines(db, statement_id=statement_id, tenant_id=tenant_id)

        for line in lines:
            vector_hits = await search_similar_payments(
                tenant_id=str(tenant_id),
                description=line.description,
                limit=5,
            )
            best_score = 0.0
            best_candidate: dict[str, Any] | None = None
            candidates_for_line: list[dict[str, Any]] = []

            for hit in vector_hits:
                vector_score = float(hit.get("vector_score", 0.0))
                vendor_name = hit.get("vendor_name") or ""
                fuzz_score = (
                    max(
                        fuzz.token_sort_ratio(line.description, vendor_name),
                        fuzz.partial_ratio(line.description, hit.get("description", "")),
                    )
                    / 100.0
                )
                combined = (vector_score * 0.6) + (fuzz_score * 0.4)
                candidate = {**hit, "combined_score": combined, "line_id": str(line.id)}

                if combined >= FUZZY_CANDIDATE_THRESHOLD:
                    candidates_for_line.append(candidate)

                if combined > best_score:
                    best_score = combined
                    best_candidate = candidate

            if best_candidate and best_score >= FUZZY_MATCH_THRESHOLD:
                payment = await db.get(Payment, uuid.UUID(best_candidate["payment_id"]))
                if payment and _amounts_equal(line.amount, payment.amount):
                    await _create_match(
                        db,
                        tenant_id=tenant_id,
                        statement_id=statement_id,
                        line=line,
                        payment=payment,
                        invoice_id=uuid.UUID(best_candidate["invoice_id"]),
                        match_type=MatchType.FUZZY,
                        confidence=best_score,
                        llm_reasoning=f"Vector+fuzzy combined score {best_score:.2f}",
                    )
                    matched_count += 1
                    continue

            if candidates_for_line:
                fuzzy_candidates.append(
                    {
                        "line_id": str(line.id),
                        "description": line.description,
                        "amount": float(line.amount),
                        "transaction_date": line.transaction_date.isoformat(),
                        "reference": line.reference,
                        "candidates": sorted(
                            candidates_for_line,
                            key=lambda item: item["combined_score"],
                            reverse=True,
                        )[:5],
                    }
                )

        await db.commit()

    return {
        **update,
        "fuzzy_matched_count": matched_count,
        "fuzzy_candidates": fuzzy_candidates,
    }


def _parse_llm_judgment(content: str) -> dict[str, Any]:
    text = content.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "matched": False,
            "confidence": 0,
            "explanation": content.strip(),
            "payment_id": None,
            "invoice_id": None,
        }


@trace_agent_step("reconciliation")
async def llm_judgment_node(state: ReconciliationState) -> dict:
    update = _agent.log_step(
        {"invoice_id": state["statement_id"], "tenant_id": state["tenant_id"]},
        "llm_judgment",
    )
    statement_id = uuid.UUID(state["statement_id"])
    tenant_id = uuid.UUID(state["tenant_id"])
    matched_count = 0
    unmatched_lines: list[dict[str, Any]] = []

    candidate_map = {
        item["line_id"]: item for item in state.get("fuzzy_candidates", [])
    }

    async with async_session_factory() as db:
        set_current_tenant_id(tenant_id)
        lines = await _get_unmatched_lines(db, statement_id=statement_id, tenant_id=tenant_id)

        for line in lines:
            candidates = candidate_map.get(str(line.id), {}).get("candidates", [])
            prompt = (
                "You are a financial reconciliation expert. Match this bank transaction to the "
                "most likely invoice/payment. Analyze transaction description, amount, date, and "
                "vendor patterns. Think step by step.\n\n"
                f"Bank line:\n"
                f"- Date: {line.transaction_date.isoformat()}\n"
                f"- Amount: {line.amount} {line.currency}\n"
                f"- Description: {line.description}\n"
                f"- Reference: {line.reference or 'N/A'}\n\n"
                f"Top candidates:\n{json.dumps(candidates, indent=2)}\n\n"
                "Return JSON only with keys: matched (boolean), confidence (0-100 integer), "
                "explanation (one sentence plain English), payment_id (uuid or null), "
                "invoice_id (uuid or null)."
            )

            response = await _agent.invoke_llm_with_routing_context(
                [{"role": "user", "content": prompt}],
                task_type="reconciliation_llm_pass",
                tenant_id=state["tenant_id"],
                risk_score=0.0,
            )
            parsed = _parse_llm_judgment(response.content)
            confidence = int(parsed.get("confidence", 0) or 0)
            explanation = parsed.get("explanation") or "No explanation provided."

            if parsed.get("matched") and confidence >= LLM_MATCH_THRESHOLD:
                payment_id = parsed.get("payment_id")
                invoice_id = parsed.get("invoice_id")
                payment = await db.get(Payment, uuid.UUID(payment_id)) if payment_id else None
                await _create_match(
                    db,
                    tenant_id=tenant_id,
                    statement_id=statement_id,
                    line=line,
                    payment=payment,
                    invoice_id=uuid.UUID(invoice_id) if invoice_id else None,
                    match_type=MatchType.LLM_JUDGMENT,
                    confidence=confidence / 100.0,
                    llm_reasoning=explanation,
                )
                matched_count += 1
            else:
                line.exception_reason = explanation
                line.llm_explanation = explanation
                unmatched_lines.append(
                    {
                        "line_id": str(line.id),
                        "amount": float(line.amount),
                        "transaction_date": line.transaction_date.isoformat(),
                        "description": line.description,
                        "explanation": explanation,
                    }
                )

        await db.commit()

    return {
        **update,
        "llm_matched_count": matched_count,
        "unmatched_lines": unmatched_lines,
        "unmatched_count": len(unmatched_lines),
    }


async def _send_report_email(
    *,
    tenant_id: uuid.UUID,
    statement: BankStatement,
    report_html: str,
) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("resend_not_configured_for_reconciliation_report")
        return

    async with async_session_factory() as db:
        set_current_tenant_id(tenant_id)
        result = await db.execute(
            select(User.email).where(
                User.tenant_id == tenant_id,
                User.role == UserRole.CONTROLLER,
                User.is_active.is_(True),
            )
        )
        recipients = [email for (email,) in result.all()]

    if not recipients:
        return

    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.email_from,
                "to": recipients,
                "subject": f"Reconciliation report: {statement.filename}",
                "html": report_html,
            },
        )


@trace_agent_step("reconciliation")
async def generate_report_node(state: ReconciliationState) -> dict:
    update = _agent.log_step(
        {"invoice_id": state["statement_id"], "tenant_id": state["tenant_id"]},
        "generate_report",
    )
    statement_id = uuid.UUID(state["statement_id"])
    tenant_id = uuid.UUID(state["tenant_id"])

    async with async_session_factory() as db:
        set_current_tenant_id(tenant_id)
        statement = await db.get(BankStatement, statement_id)
        if statement is None:
            return {**update, "error": "statement_not_found"}

        total_result = await db.execute(
            select(func.count())
            .select_from(BankStatementLine)
            .where(BankStatementLine.statement_id == statement_id)
        )
        total_lines = total_result.scalar_one()

        match_counts_result = await db.execute(
            select(ReconciliationMatch.match_type, func.count())
            .where(ReconciliationMatch.statement_id == statement_id)
            .group_by(ReconciliationMatch.match_type)
        )
        counts = {match_type.value: count for match_type, count in match_counts_result.all()}

        exact = counts.get(MatchType.EXACT.value, 0)
        fuzzy = counts.get(MatchType.FUZZY.value, 0)
        llm = counts.get(MatchType.LLM_JUDGMENT.value, 0)
        manual = counts.get(MatchType.MANUAL.value, 0)
        matched_total = exact + fuzzy + llm + manual
        unmatched = max(total_lines - matched_total, 0)

        def pct(value: int) -> float:
            return round((value / total_lines) * 100, 2) if total_lines else 0.0

        unmatched_lines_result = await db.execute(
            select(BankStatementLine).where(
                BankStatementLine.statement_id == statement_id,
                BankStatementLine.is_matched.is_(False),
            )
        )
        unmatched_line_rows = list(unmatched_lines_result.scalars().all())
        unmatched_explanations: list[str] = []

        for line in unmatched_line_rows:
            reason = line.llm_explanation or line.exception_reason or "No close payment candidate found."
            suggested = "Manual review recommended."
            if "reference" in reason.lower():
                suggested = "Verify payment reference with the vendor."
            elif "vendor" in reason.lower():
                suggested = "Check with vendor to confirm payment details."
            explanation = (
                f"This {line.currency} {line.amount} payment from {line.transaction_date.isoformat()} "
                f"with description '{line.description}' could not be matched. "
                f"Possible reason: {reason} Suggested action: {suggested}"
            )
            line.exception_reason = explanation
            unmatched_explanations.append(explanation)

        summary = {
            "total_lines": total_lines,
            "matched_lines": matched_total,
            "unmatched_lines": unmatched,
            "exact_matched": exact,
            "exact_pct": pct(exact),
            "fuzzy_matched": fuzzy,
            "fuzzy_pct": pct(fuzzy),
            "llm_matched": llm,
            "llm_pct": pct(llm),
            "manual_matched": manual,
            "unmatched_pct": pct(unmatched),
            "match_rate": pct(matched_total),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        statement.status = StatementStatus.COMPLETED
        statement.report_summary = summary
        await db.commit()

        report_html = (
            f"<h2>Reconciliation Report: {statement.filename}</h2>"
            f"<p><strong>Total lines:</strong> {total_lines}</p>"
            f"<p><strong>Exact matched:</strong> {exact} ({pct(exact)}%)</p>"
            f"<p><strong>Fuzzy matched:</strong> {fuzzy} ({pct(fuzzy)}%)</p>"
            f"<p><strong>LLM matched:</strong> {llm} ({pct(llm)}%)</p>"
            f"<p><strong>Unmatched:</strong> {unmatched} ({pct(unmatched)}%)</p>"
            f"<h3>Unmatched explanations</h3><ul>"
            + "".join(f"<li>{item}</li>" for item in unmatched_explanations)
            + "</ul>"
        )
        await _send_report_email(
            tenant_id=tenant_id,
            statement=statement,
            report_html=report_html,
        )

    return {**update, "report": summary}


def build_reconciliation_graph():
    graph = StateGraph(ReconciliationState)
    graph.add_node("exact_match", exact_match_node)
    graph.add_node("fuzzy_match", fuzzy_match_node)
    graph.add_node("llm_judgment", llm_judgment_node)
    graph.add_node("generate_report", generate_report_node)

    graph.add_edge(START, "exact_match")
    graph.add_edge("exact_match", "fuzzy_match")
    graph.add_edge("fuzzy_match", "llm_judgment")
    graph.add_edge("llm_judgment", "generate_report")
    graph.add_edge("generate_report", END)
    return graph.compile()


reconciliation_graph = build_reconciliation_graph()


async def run_reconciliation_pipeline(*, statement_id: str, tenant_id: str) -> dict[str, Any]:
    initial_state = create_reconciliation_state(
        statement_id=statement_id,
        tenant_id=tenant_id,
    )
    result = await reconciliation_graph.ainvoke(initial_state)
    logger.info(
        "reconciliation_pipeline_complete",
        statement_id=statement_id,
        tenant_id=tenant_id,
        report=result.get("report"),
    )
    return result
