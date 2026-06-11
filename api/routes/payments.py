import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, select

from api.deps import ApClerkUser, DbSession
from models.payment import Payment, PaymentStatus
from schemas.payment import PaymentListResponse, PaymentResponse

router = APIRouter(tags=["payments"])


@router.get("/", response_model=PaymentListResponse)
async def list_payments(
    db: DbSession,
    current_user: ApClerkUser,
    status_filter: PaymentStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaymentListResponse:
    filters = [Payment.tenant_id == current_user.tenant_id]
    if status_filter:
        filters.append(Payment.status == status_filter)

    count_result = await db.execute(
        select(func.count()).select_from(Payment).where(and_(*filters))
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Payment)
        .where(and_(*filters))
        .order_by(Payment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    return PaymentListResponse(items=items, total=total)


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: uuid.UUID,
    db: DbSession,
    current_user: ApClerkUser,
) -> Payment:
    result = await db.execute(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.tenant_id == current_user.tenant_id,
        )
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment
