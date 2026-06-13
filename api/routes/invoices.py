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
    ExtractionCorrectionRequest,
    InvoiceApproveRequest,
    InvoiceListResponse,
    InvoiceRejectRequest,
    InvoiceResponse,
    InvoiceRetryExtractionResponse,
    InvoiceRouteApprovalResponse,
    InvoiceUploadResponse,
)
from services.invoice_pipeline import build_state_from_invoice, run_invoice_pipeline
from services.audit import log_audit_event
from services.extraction_quality import log_human_correction_score
from services.graph_resume import resume_invoice_approval
from services.mem0_corrections import store_vendor_correction_pattern

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
    file_b64 = base64.b64encode(file_bytes).decode("utf-8")
    invoice = Invoice(
        tenant_id=current_user.tenant_id,
        vendor_id=vendor_id,
        invoice_number=f"PENDING-{uuid.uuid4().hex[:12].upper()}",
        amount=Decimal("0.00"),
        currency="USD",
        status=InvoiceStatus.RECEIVED,
        line_items=[],
        flags={
            "upload_filename": file.filename,
            "upload_content_type": file.content_type,
            "file_base64": file_b64,
        },
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
            "file_base64": file_b64,
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


@router.post(
    "/{invoice_id}/retry-extraction",
    response_model=InvoiceRetryExtractionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_invoice_extraction(
    invoice_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: ApClerkUser,
    producer: ProducerDep,
) -> InvoiceRetryExtractionResponse:
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    flags = invoice.flags or {}
    file_b64 = flags.get("file_base64")
    content_type = flags.get("upload_content_type", "application/pdf")
    if not file_b64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Original upload file is not stored for this invoice. Re-upload the document.",
        )

    old_status = invoice.status
    invoice.status = InvoiceStatus.RECEIVED
    await producer.send(
        TOPIC_INVOICE_RECEIVED,
        {
            "invoice_id": str(invoice.id),
            "tenant_id": str(current_user.tenant_id),
            "vendor_id": str(invoice.vendor_id),
            "filename": flags.get("upload_filename", "invoice.pdf"),
            "content_type": content_type,
            "file_base64": file_b64,
            "uploaded_by": str(current_user.id),
            "retry": True,
        },
        key=str(invoice.id),
    )

    await log_audit_event(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="extraction_retry_requested",
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        old_value={"status": old_status.value},
        new_value={"status": InvoiceStatus.RECEIVED.value},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return InvoiceRetryExtractionResponse(
        invoice_id=invoice.id,
        status=invoice.status,
        message="Invoice re-queued for extraction",
    )


@router.post(
    "/{invoice_id}/route-approval",
    response_model=InvoiceRouteApprovalResponse,
    status_code=status.HTTP_200_OK,
)
async def route_invoice_approval(
    invoice_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: ApClerkUser,
) -> InvoiceRouteApprovalResponse:
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if not invoice.extracted_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice has no extracted data. Run extraction first.",
        )

    if invoice.status not in {
        InvoiceStatus.MATCHED,
        InvoiceStatus.REVIEW_REQUIRED,
        InvoiceStatus.RECEIVED,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot route approval from status '{invoice.status.value}'",
        )

    old_status = invoice.status
    state = build_state_from_invoice(invoice)
    try:
        await run_invoice_pipeline(state)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Approval routing failed: {exc}",
        ) from exc

    db.expire_all()
    refreshed = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    invoice = refreshed.scalar_one()
    required_role = (invoice.flags or {}).get("required_role")

    await log_audit_event(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="approval_routing_requested",
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        old_value={"status": old_status.value},
        new_value={
            "status": invoice.status.value,
            "required_role": required_role,
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return InvoiceRouteApprovalResponse(
        invoice_id=invoice.id,
        status=invoice.status,
        required_role=required_role,
        message="Invoice routed through approval policy",
    )


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
            invoice_id=str(invoice_id),
            tenant_id=str(current_user.tenant_id),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unable to resume approval workflow: {exc}",
        ) from exc

    db.expire_all()
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
            invoice_id=str(invoice_id),
            tenant_id=str(current_user.tenant_id),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unable to resume approval workflow: {exc}",
        ) from exc

    db.expire_all()
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    return result.scalar_one()


@router.patch("/{invoice_id}/correct-extraction", response_model=InvoiceResponse)
async def correct_invoice_extraction(
    invoice_id: uuid.UUID,
    payload: ExtractionCorrectionRequest,
    request: Request,
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

    old_extracted = dict(invoice.extracted_data or {})
    corrected = {**old_extracted, **payload.corrections}

    if "total_amount" in payload.corrections:
        invoice.amount = Decimal(str(payload.corrections["total_amount"]))
    if "invoice_number" in payload.corrections:
        invoice.invoice_number = str(payload.corrections["invoice_number"])
    if "due_date" in payload.corrections and payload.corrections["due_date"]:
        from datetime import date as date_type

        invoice.due_date = date_type.fromisoformat(str(payload.corrections["due_date"]))
    if "currency" in payload.corrections:
        invoice.currency = str(payload.corrections["currency"]).upper()[:3]
    if "line_items" in payload.corrections:
        invoice.line_items = payload.corrections["line_items"]

    invoice.extracted_data = corrected
    await log_human_correction_score(
        invoice=invoice,
        corrected_fields=list(payload.corrections.keys()),
        corrections=payload.corrections,
    )

    await store_vendor_correction_pattern(
        tenant_id=str(current_user.tenant_id),
        vendor_id=str(invoice.vendor_id),
        corrections=payload.corrections,
        corrected_data=corrected,
    )

    await log_audit_event(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="extraction_corrected",
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        old_value={"extracted_data": old_extracted},
        new_value={"extracted_data": corrected, "corrections": payload.corrections},
        reason=payload.notes,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice


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
