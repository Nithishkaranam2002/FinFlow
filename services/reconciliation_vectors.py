"""Embedding and vector search helpers for reconciliation."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from openai import AsyncOpenAI
from qdrant_client.http.models import FieldCondition, Filter, MatchValue, PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import get_settings
from core.qdrant import EMBEDDING_DIMENSION, RECONCILIATION_COLLECTION, ensure_reconciliation_collection, get_qdrant_client
from models.invoice import Invoice
from models.payment import Payment
from models.vendor import Vendor

logger = structlog.get_logger(__name__)
EMBEDDING_MODEL = "text-embedding-3-small"


async def embed_text(text: str) -> list[float]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key or None)
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text[:8000],
    )
    return response.data[0].embedding


async def index_tenant_payments(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    ensure_reconciliation_collection()
    client = get_qdrant_client()

    result = await db.execute(
        select(Payment)
        .options(selectinload(Payment.invoice).selectinload(Invoice.vendor))
        .where(Payment.tenant_id == tenant_id)
    )
    payments = result.scalars().all()
    if not payments:
        return 0

    points: list[PointStruct] = []
    for payment in payments:
        invoice = payment.invoice
        vendor_name = invoice.vendor.name if invoice and invoice.vendor else ""
        invoice_number = invoice.invoice_number if invoice else ""
        description = " ".join(
            part
            for part in (
                vendor_name,
                invoice_number,
                payment.payment_reference or "",
                payment.bank_transaction_id or "",
            )
            if part
        ).strip()
        if not description:
            continue

        vector = await embed_text(description)
        if len(vector) != EMBEDDING_DIMENSION:
            logger.warning("unexpected_embedding_dimension", dimension=len(vector))
            continue

        points.append(
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{tenant_id}:{payment.id}")),
                vector=vector,
                payload={
                    "tenant_id": str(tenant_id),
                    "payment_id": str(payment.id),
                    "invoice_id": str(payment.invoice_id),
                    "vendor_name": vendor_name,
                    "description": description,
                    "amount": float(payment.amount),
                    "payment_reference": payment.payment_reference,
                },
            )
        )

    if points:
        client.upsert(collection_name=RECONCILIATION_COLLECTION, points=points)

    logger.info("tenant_payments_indexed", tenant_id=str(tenant_id), count=len(points))
    return len(points)


async def search_similar_payments(
    *,
    tenant_id: str,
    description: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    ensure_reconciliation_collection()
    client = get_qdrant_client()
    vector = await embed_text(description)

    results = client.search(
        collection_name=RECONCILIATION_COLLECTION,
        query_vector=vector,
        limit=limit,
        query_filter=Filter(
            must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        ),
    )

    return [
        {
            "payment_id": hit.payload.get("payment_id"),
            "invoice_id": hit.payload.get("invoice_id"),
            "vendor_name": hit.payload.get("vendor_name"),
            "description": hit.payload.get("description"),
            "amount": hit.payload.get("amount"),
            "payment_reference": hit.payload.get("payment_reference"),
            "vector_score": float(hit.score),
        }
        for hit in results
        if hit.payload
    ]


async def load_vendor_names(db: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    result = await db.execute(select(Vendor.name).where(Vendor.tenant_id == tenant_id))
    return [name for (name,) in result.all()]
