import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.deps import ApClerkUser, ControllerUser, DbSession
from models.invoice import Invoice
from models.payment import Payment
from models.vendor import Vendor
from schemas.invoice import InvoiceResponse
from schemas.payment import PaymentResponse
from schemas.vendor import VendorCreate, VendorDetailResponse, VendorResponse

router = APIRouter(tags=["vendors"])


@router.post("/", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    db: DbSession,
    current_user: ControllerUser,
) -> Vendor:
    vendor = Vendor(
        tenant_id=current_user.tenant_id,
        name=payload.name,
        email=payload.email,
        bank_account=payload.bank_account,
        payment_terms_days=payload.payment_terms_days,
    )
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.get("/", response_model=list[VendorResponse])
async def list_vendors(
    db: DbSession,
    current_user: ApClerkUser,
) -> list[Vendor]:
    result = await db.execute(
        select(Vendor)
        .where(Vendor.tenant_id == current_user.tenant_id)
        .order_by(Vendor.risk_score.desc(), Vendor.name.asc())
    )
    return list(result.scalars().all())


@router.get("/{vendor_id}", response_model=VendorDetailResponse)
async def get_vendor(
    vendor_id: uuid.UUID,
    db: DbSession,
    current_user: ApClerkUser,
) -> VendorDetailResponse:
    result = await db.execute(
        select(Vendor)
        .options(selectinload(Vendor.invoices).selectinload(Invoice.payments))
        .where(
            Vendor.id == vendor_id,
            Vendor.tenant_id == current_user.tenant_id,
        )
    )
    vendor = result.scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    payments: list[Payment] = []
    for invoice in vendor.invoices:
        payments.extend(invoice.payments)

    return VendorDetailResponse(
        **VendorResponse.model_validate(vendor).model_dump(),
        invoices=[InvoiceResponse.model_validate(i) for i in vendor.invoices],
        payments=[PaymentResponse.model_validate(p) for p in payments],
    )
