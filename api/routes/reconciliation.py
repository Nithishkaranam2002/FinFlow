import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, select

from api.deps import ApClerkUser, DbSession
from models.reconciliation import MatchType, ReconciliationMatch
from schemas.reconciliation import ReconciliationListResponse, ReconciliationMatchResponse

router = APIRouter(tags=["reconciliation"])


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
