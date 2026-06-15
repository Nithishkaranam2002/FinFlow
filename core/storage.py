"""S3-compatible object storage for invoice documents (MinIO in dev, S3 in prod)."""

from __future__ import annotations

import structlog
from botocore.exceptions import ClientError

from core.config import get_settings

logger = structlog.get_logger(__name__)


def _client():
    import boto3
    from botocore.client import Config

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
        config=Config(signature_version="s3v4"),
    )


def invoice_storage_key(tenant_id: str, invoice_id: str, filename: str) -> str:
    safe_name = (filename or "document.pdf").replace("/", "_")
    return f"tenants/{tenant_id}/invoices/{invoice_id}/{safe_name}"


def ensure_bucket() -> None:
    settings = get_settings()
    client = _client()
    bucket = settings.s3_bucket
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
        logger.info("s3_bucket_created", bucket=bucket)


def upload_document(key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    _client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    logger.info("document_uploaded", key=key, size=len(data))


def download_document(key: str) -> bytes:
    settings = get_settings()
    response = _client().get_object(Bucket=settings.s3_bucket, Key=key)
    return response["Body"].read()


def delete_document(key: str) -> None:
    settings = get_settings()
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)
