from unittest.mock import MagicMock, patch

import pytest

from services.invoice_documents import (
    build_invoice_kafka_payload,
    invoice_flags_for_upload,
    load_invoice_bytes,
)


def test_build_invoice_kafka_payload_uses_storage_key() -> None:
    import uuid

    invoice_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    vendor_id = uuid.uuid4()
    uploaded_by = uuid.uuid4()

    payload = build_invoice_kafka_payload(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        vendor_id=vendor_id,
        filename="invoice.pdf",
        content_type="application/pdf",
        storage_key="tenants/x/invoices/y/invoice.pdf",
        uploaded_by=uploaded_by,
    )

    assert payload["storage_key"] == "tenants/x/invoices/y/invoice.pdf"
    assert "file_base64" not in payload


def test_invoice_flags_for_upload() -> None:
    flags = invoice_flags_for_upload(
        filename="invoice.pdf",
        content_type="application/pdf",
        storage_key="tenants/a/invoices/b/invoice.pdf",
    )
    assert flags["storage_key"] == "tenants/a/invoices/b/invoice.pdf"
    assert "file_base64" not in flags


@patch("services.invoice_documents.download_document")
def test_load_invoice_bytes_prefers_storage_key(mock_download: MagicMock) -> None:
    mock_download.return_value = b"pdf-bytes"
    assert load_invoice_bytes(storage_key="key", file_base64="Zm9v") == b"pdf-bytes"
    mock_download.assert_called_once_with("key")


def test_load_invoice_bytes_legacy_base64() -> None:
    import base64

    payload = base64.b64encode(b"legacy").decode()
    assert load_invoice_bytes(file_base64=payload) == b"legacy"


def test_load_invoice_bytes_missing_reference() -> None:
    with pytest.raises(ValueError, match="No document reference"):
        load_invoice_bytes()
