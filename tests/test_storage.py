from unittest.mock import MagicMock, patch

from core.storage import invoice_storage_key, upload_document


def test_invoice_storage_key_format() -> None:
    key = invoice_storage_key("tenant-1", "invoice-2", "my invoice.pdf")
    assert key == "tenants/tenant-1/invoices/invoice-2/my invoice.pdf"


@patch("core.storage._client")
def test_upload_document_puts_object(mock_client_factory: MagicMock, monkeypatch) -> None:
    monkeypatch.setenv("S3_BUCKET", "finflow-documents")
    client = MagicMock()
    mock_client_factory.return_value = client

    upload_document("tenants/a/invoices/b/file.pdf", b"data", "application/pdf")

    client.put_object.assert_called_once()
    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "finflow-documents"
    assert kwargs["Key"] == "tenants/a/invoices/b/file.pdf"
    assert kwargs["Body"] == b"data"
