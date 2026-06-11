import base64
import uuid
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import and_, func, select

from api.deps import ApClerkUser, CurrentUser, DbSession
from core.kafka import TOPIC_INVOICE_RECEIVED, ProducerDep
from core.rbac import user_meets_required_role
from models.audit import AuditLog
from models.invoice import Invoice, InvoiceStatus
from models.vendor import Vendor
from schemas.invoice import (
    AuditLogResponse,
    InvoiceApproveRequest,
    InvoiceListResponse,
    InvoiceRejectRequest,
    InvoiceResponse,
    InvoiceUploadResponse,
)
from services.audit import log_audit_event
from services.graph_resume import resume_invoice_approval

router = APIRouter(tags=["invoices"])

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
}


@router.post("/upload", response_model=InvoiceUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_invoice(
    request: Request,
    db: DbSession,
    current_user: ApClerkUser,
    producer: ProducerDep,
    file: UploadFile = File(...),
    vendor_id: uuid.UUID = Form(...),
) -> InvoiceUploadResponse:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and image files are supported",
        )

    vendor_result = await db.execute(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.tenant_id == current_user.tenant_id,
        )
    )
    if vendor_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    file_bytes = await file.read()
    invoice = Invoice(
        tenant_id=current_user.tenant_id,
        vendor_id=vendor_id,
        invoice_number=f"PENDING-{uuid.uuid4().hex[:12].upper()}",
        amount=Decimal("0.00"),
        currency="USD",
        status=InvoiceStatus.RECEIVED,
        line_items=[],
        flags={},
    )
    db.add(invoice)
    await db.flush()

    await producer.send(
        TOPIC_INVOICE_RECEIVED,
        {
            "invoice_id": str(invoice.id),
            "tenant_id": str(current_user.tenant_id),
            "vendor_id": str(vendor_id),
            "filename": file.filename,
            "content_type": file.content_type,
            "file_base64": base64.b64encode(file_bytes).decode("utf-8"),
            "uploaded_by": str(current_user.id),
        },
        key=str(invoice.id),
    )

    await log_audit_event(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="uploaded",
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        new_value={"status": InvoiceStatus.RECEIVED.value, "filename": file.filename},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return InvoiceUploadResponse(invoice_id=invoice.id, status=invoice.status)


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    db: DbSession,
    current_user: ApClerkUser,
    status_filter: InvoiceStatus | None = Query(default=None, alias="status"),
    vendor_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> InvoiceListResponse:
    filters = [Invoice.tenant_id == current_user.tenant_id]
    if status_filter:
        filters.append(Invoice.status == status_filter)
    if vendor_id:
        filters.append(Invoice.vendor_id == vendor_id)
    if date_from:
        filters.append(func.date(Invoice.created_at) >= date_from)
    if date_to:
        filters.append(func.date(Invoice.created_at) <= date_to)

    count_result = await db.execute(
        select(func.count()).select_from(Invoice).where(and_(*filters))
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Invoice)
        .where(and_(*filters))
        .order_by(Invoice.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    return InvoiceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    db: DbSession,
    current_user: ApClerkUser,
) -> Invoice:
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@router.patch("/{invoice_id}/approve", response_model=InvoiceResponse)
async def approve_invoice(
    invoice_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    payload: InvoiceApproveRequest | None = None,
) -> Invoice:
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.status not in {InvoiceStatus.PENDING_APPROVAL, InvoiceStatus.REVIEW_REQUIRED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is not awaiting approval",
        )

    required_role = (invoice.flags or {}).get("required_role", "approver")
    if not user_meets_required_role(current_user, required_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires {required_role} role or higher",
        )

    thread_id = (invoice.flags or {}).get("thread_id", str(invoice_id))
    notes = payload.notes if payload else None

    try:
        await resume_invoice_approval(
            thread_id=thread_id,
            decision="approved",
            approver_id=str(current_user.id),
            notes=notes or "",
            approver_role=current_user.role.value,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unable to resume approval workflow: {exc}",
        ) from exc

    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    return result.scalar_one()


@router.patch("/{invoice_id}/reject", response_model=InvoiceResponse)
async def reject_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceRejectRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> Invoice:
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.status not in {InvoiceStatus.PENDING_APPROVAL, InvoiceStatus.REVIEW_REQUIRED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is not awaiting approval",
        )

    required_role = (invoice.flags or {}).get("required_role", "approver")
    if not user_meets_required_role(current_user, required_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires {required_role} role or higher",
        )

    thread_id = (invoice.flags or {}).get("thread_id", str(invoice_id))

    try:
        await resume_invoice_approval(
            thread_id=thread_id,
            decision="rejected",
            approver_id=str(current_user.id),
            notes=payload.reason,
            approver_role=current_user.role.value,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unable to resume approval workflow: {exc}",
        ) from exc

    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    return result.scalar_one()


@router.get("/{invoice_id}/audit-trail", response_model=list[AuditLogResponse])
async def get_invoice_audit_trail(
    invoice_id: uuid.UUID,
    db: DbSession,
    current_user: ApClerkUser,
) -> list[AuditLog]:
    invoice_result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    if invoice_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.entity_type == "invoice",
            AuditLog.entity_id == invoice_id,
        )
        .order_by(AuditLog.created_at.desc())
    )
    return list(result.scalars().all())
