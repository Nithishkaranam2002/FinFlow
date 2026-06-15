"""Store and load invoice documents via S3-compatible object storage."""

from __future__ import annotations

import base64
import uuid
from typing import Any

from core.storage import download_document, invoice_storage_key, upload_document


def store_invoice_file(
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    file_bytes: bytes,
    filename: str | None,
    content_type: str,
) -> str:
    key = invoice_storage_key(str(tenant_id), str(invoice_id), filename or "document.pdf")
    upload_document(key, file_bytes, content_type)
    return key


def build_invoice_kafka_payload(
    *,
    invoice_id: uuid.UUID,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    filename: str | None,
    content_type: str,
    storage_key: str,
    uploaded_by: uuid.UUID,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "invoice_id": str(invoice_id),
        "tenant_id": str(tenant_id),
        "vendor_id": str(vendor_id),
        "filename": filename,
        "content_type": content_type,
        "storage_key": storage_key,
        "uploaded_by": str(uploaded_by),
        **extra,
    }


def load_invoice_bytes(*, storage_key: str | None = None, file_base64: str | None = None) -> bytes:
    if storage_key:
        return download_document(storage_key)
    if file_base64:
        return base64.b64decode(file_base64)
    raise ValueError("No document reference available for invoice")


def invoice_flags_for_upload(
    *,
    filename: str | None,
    content_type: str | None,
    storage_key: str,
) -> dict[str, str]:
    return {
        "upload_filename": filename or "document.pdf",
        "upload_content_type": content_type or "application/pdf",
        "storage_key": storage_key,
    }
