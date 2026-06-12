"""Qdrant vector database client for reconciliation similarity search."""

from __future__ import annotations

from functools import lru_cache

import structlog
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from core.config import get_settings

logger = structlog.get_logger(__name__)

RECONCILIATION_COLLECTION = "finflow_reconciliation"
EMBEDDING_DIMENSION = 1536


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    logger.info("qdrant_client_initialized", url=settings.qdrant_url)
    return client


def ensure_reconciliation_collection() -> None:
    client = get_qdrant_client()
    collections = {collection.name for collection in client.get_collections().collections}
    if RECONCILIATION_COLLECTION in collections:
        return

    client.create_collection(
        collection_name=RECONCILIATION_COLLECTION,
        vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
    )
    logger.info("qdrant_collection_created", collection=RECONCILIATION_COLLECTION)
