import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, func, select

from api.deps import ApClerkUser, ControllerUser, DbSession
from core.kafka import TOPIC_RECONCILIATION_STARTED, ProducerDep
from models.invoice import Invoice
from models.payment import Payment
from models.reconciliation import (
    BankStatement,
    BankStatementLine,
    MatchType,
    ReconciliationMatch,
    StatementStatus,
)
from schemas.reconciliation import (
    ManualMatchRequest,
    ReconciliationExceptionItem,
    ReconciliationExceptionListResponse,
    ReconciliationListResponse,
    ReconciliationMatchResponse,
    ReconciliationReportLine,
    ReconciliationReportResponse,
    ReconciliationStatusResponse,
    BankStatementUploadResponse,
)
from services.statement_parser import parse_statement_file

router = APIRouter(tags=["reconciliation"])

ALLOWED_STATEMENT_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    "application/octet-stream",
}


@router.post("/upload-statement", response_model=BankStatementUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_bank_statement(
    db: DbSession,
    current_user: ApClerkUser,
    producer: ProducerDep,
    file: UploadFile = File(...),
) -> BankStatementUploadResponse:
    if file.content_type not in ALLOWED_STATEMENT_TYPES and not (
        file.filename and (file.filename.lower().endswith(".csv") or file.filename.lower().endswith(".mt940"))
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV or MT940 statement files are supported",
        )

    content = await file.read()
    try:
        source_format, parsed_lines = parse_statement_file(
            content,
            file.filename or "statement.csv",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not parsed_lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No transactions found in statement")

    statement = BankStatement(
        tenant_id=current_user.tenant_id,
        filename=file.filename or "statement.csv",
        source_format=source_format,
        statement_date=next((line.statement_date for line in parsed_lines if line.statement_date), None),
        status=StatementStatus.PROCESSING,
        line_count=len(parsed_lines),
    )
    db.add(statement)
    await db.flush()

    for parsed in parsed_lines:
        db.add(
            BankStatementLine(
                tenant_id=current_user.tenant_id,
                statement_id=statement.id,
                statement_date=parsed.statement_date,
                transaction_date=parsed.transaction_date,
                description=parsed.description,
                amount=parsed.amount,
                reference=parsed.reference,
                bank_transaction_id=parsed.bank_transaction_id,
                currency=parsed.currency,
            )
        )

    await db.commit()
    await db.refresh(statement)

    await producer.send(
        TOPIC_RECONCILIATION_STARTED,
        {
            "bank_statement_id": str(statement.id),
            "tenant_id": str(current_user.tenant_id),
            "total_lines": statement.line_count,
            "filename": statement.filename,
        },
        key=str(statement.id),
    )

    return BankStatementUploadResponse(
        statement_id=statement.id,
        line_count=statement.line_count,
        status=statement.status,
    )


@router.get("/status/{statement_id}", response_model=ReconciliationStatusResponse)
async def get_reconciliation_status(
    statement_id: uuid.UUID,
    db: DbSession,
    current_user: ApClerkUser,
) -> ReconciliationStatusResponse:
    statement = await _get_statement(db, statement_id, current_user.tenant_id)

    total = await _count_lines(db, statement_id)
    matched = await _count_lines(db, statement_id, matched=True)
    unmatched = total - matched
    pending = unmatched if statement.status == StatementStatus.PROCESSING else 0

    match_counts = await _match_type_counts(db, statement_id)
    summary = statement.report_summary or {}

    return ReconciliationStatusResponse(
        statement_id=statement.id,
        status=statement.status,
        total_lines=total,
        matched_lines=matched,
        pending_lines=pending,
        unmatched_lines=unmatched,
        match_rate=float(summary.get("match_rate", (matched / total * 100) if total else 0.0)),
        exact_matched=match_counts.get(MatchType.EXACT.value, 0),
        fuzzy_matched=match_counts.get(MatchType.FUZZY.value, 0),
        llm_matched=match_counts.get(MatchType.LLM_JUDGMENT.value, 0),
        manual_matched=match_counts.get(MatchType.MANUAL.value, 0),
    )


@router.get("/exceptions", response_model=ReconciliationExceptionListResponse)
async def list_reconciliation_exceptions(
    db: DbSession,
    current_user: ApClerkUser,
    statement_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ReconciliationExceptionListResponse:
    filters = [
        BankStatementLine.tenant_id == current_user.tenant_id,
        BankStatementLine.is_matched.is_(False),
    ]
    if statement_id:
        filters.append(BankStatementLine.statement_id == statement_id)

    total_result = await db.execute(
        select(func.count()).select_from(BankStatementLine).where(and_(*filters))
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(BankStatementLine)
        .where(and_(*filters))
        .order_by(BankStatementLine.transaction_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    lines = result.scalars().all()

    items = [
        ReconciliationExceptionItem(
            line_id=line.id,
            transaction_date=line.transaction_date,
            description=line.description,
            amount=line.amount,
            currency=line.currency,
            reference=line.reference,
            llm_explanation=line.llm_explanation,
            exception_reason=line.exception_reason,
            suggested_action=_suggested_action(line.exception_reason or line.llm_explanation),
        )
        for line in lines
    ]
    return ReconciliationExceptionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/exceptions/{line_id}/manual-match", response_model=ReconciliationMatchResponse)
async def manual_match_exception(
    line_id: uuid.UUID,
    payload: ManualMatchRequest,
    db: DbSession,
    current_user: ControllerUser,
) -> ReconciliationMatch:
    line_result = await db.execute(
        select(BankStatementLine).where(
            BankStatementLine.id == line_id,
            BankStatementLine.tenant_id == current_user.tenant_id,
        )
    )
    line = line_result.scalar_one_or_none()
    if line is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank line not found")
    if line.is_matched:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Line is already matched")

    invoice_result = await db.execute(
        select(Invoice).where(
            Invoice.id == payload.invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    if invoice_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    payment = None
    if payload.payment_id:
        payment_result = await db.execute(
            select(Payment).where(
                Payment.id == payload.payment_id,
                Payment.tenant_id == current_user.tenant_id,
            )
        )
        payment = payment_result.scalar_one_or_none()
        if payment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    line.is_matched = True
    match = ReconciliationMatch(
        tenant_id=current_user.tenant_id,
        statement_id=line.statement_id,
        bank_statement_line_id=line.id,
        bank_line_id=str(line.id),
        invoice_id=payload.invoice_id,
        payment_id=payload.payment_id,
        match_type=MatchType.MANUAL,
        confidence_score=1.0,
        llm_reasoning=payload.notes,
        matched_by=str(current_user.id),
        matched_at=datetime.now(timezone.utc),
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match


@router.get("/report/{statement_id}", response_model=ReconciliationReportResponse)
async def get_reconciliation_report(
    statement_id: uuid.UUID,
    db: DbSession,
    current_user: ApClerkUser,
) -> ReconciliationReportResponse:
    statement = await _get_statement(db, statement_id, current_user.tenant_id)

    lines_result = await db.execute(
        select(BankStatementLine)
        .where(
            BankStatementLine.statement_id == statement_id,
            BankStatementLine.tenant_id == current_user.tenant_id,
        )
        .order_by(BankStatementLine.transaction_date.asc())
    )
    lines = lines_result.scalars().all()

    matches_result = await db.execute(
        select(ReconciliationMatch).where(
            ReconciliationMatch.statement_id == statement_id,
            ReconciliationMatch.tenant_id == current_user.tenant_id,
        )
    )
    matches = {
        match.bank_statement_line_id: match
        for match in matches_result.scalars().all()
        if match.bank_statement_line_id
    }

    report_lines: list[ReconciliationReportLine] = []
    unmatched_explanations: list[str] = []
    for line in lines:
        match = matches.get(line.id)
        if match is None and not line.is_matched:
            unmatched_explanations.append(
                line.exception_reason
                or line.llm_explanation
                or f"Unmatched line {line.description}"
            )
        report_lines.append(
            ReconciliationReportLine(
                line_id=line.id,
                transaction_date=line.transaction_date,
                description=line.description,
                amount=line.amount,
                currency=line.currency,
                match_type=match.match_type if match else None,
                confidence_score=match.confidence_score if match else None,
                invoice_id=match.invoice_id if match else None,
                payment_id=match.payment_id if match else None,
                llm_reasoning=match.llm_reasoning if match else line.llm_explanation,
                exception_reason=line.exception_reason,
            )
        )

    summary = statement.report_summary or {}
    return ReconciliationReportResponse(
        statement_id=statement.id,
        filename=statement.filename,
        status=statement.status,
        generated_at=datetime.now(timezone.utc),
        summary=summary,
        lines=report_lines,
        unmatched_explanations=unmatched_explanations,
    )


@router.get("/", response_model=ReconciliationListResponse)
async def list_reconciliation_matches(
    db: DbSession,
    current_user: ApClerkUser,
    match_type: MatchType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ReconciliationListResponse:
    filters = [ReconciliationMatch.tenant_id == current_user.tenant_id]
    if match_type:
        filters.append(ReconciliationMatch.match_type == match_type)

    count_result = await db.execute(
        select(func.count()).select_from(ReconciliationMatch).where(and_(*filters))
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(ReconciliationMatch)
        .where(and_(*filters))
        .order_by(ReconciliationMatch.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    return ReconciliationListResponse(items=items, total=total)


@router.get("/{match_id}", response_model=ReconciliationMatchResponse)
async def get_reconciliation_match(
    match_id: uuid.UUID,
    db: DbSession,
    current_user: ApClerkUser,
) -> ReconciliationMatch:
    result = await db.execute(
        select(ReconciliationMatch).where(
            ReconciliationMatch.id == match_id,
            ReconciliationMatch.tenant_id == current_user.tenant_id,
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    return match


async def _get_statement(
    db: DbSession,
    statement_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> BankStatement:
    result = await db.execute(
        select(BankStatement).where(
            BankStatement.id == statement_id,
            BankStatement.tenant_id == tenant_id,
        )
    )
    statement = result.scalar_one_or_none()
    if statement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Statement not found")
    return statement


async def _count_lines(
    db: DbSession,
    statement_id: uuid.UUID,
    *,
    matched: bool | None = None,
) -> int:
    filters = [BankStatementLine.statement_id == statement_id]
    if matched is not None:
        filters.append(BankStatementLine.is_matched.is_(matched))
    result = await db.execute(
        select(func.count()).select_from(BankStatementLine).where(and_(*filters))
    )
    return result.scalar_one()


async def _match_type_counts(db: DbSession, statement_id: uuid.UUID) -> dict[str, int]:
    result = await db.execute(
        select(ReconciliationMatch.match_type, func.count())
        .where(ReconciliationMatch.statement_id == statement_id)
        .group_by(ReconciliationMatch.match_type)
    )
    return {match_type.value: count for match_type, count in result.all()}


def _suggested_action(reason: str | None) -> str | None:
    if not reason:
        return "Manual review recommended."
    lower = reason.lower()
    if "reference" in lower:
        return "Verify payment reference with the vendor."
    if "vendor" in lower:
        return "Check with vendor to confirm payment details."
    return "Manual review recommended."
