"""Mem0-backed vendor extraction correction memory."""

from __future__ import annotations

import json
from typing import Any

import structlog

from core.config import get_settings

logger = structlog.get_logger(__name__)


def _mem0_user_id(tenant_id: str, vendor_id: str) -> str:
    return f"{tenant_id}:{vendor_id}"


def _get_mem0_client():
    settings = get_settings()
    if not settings.mem0_api_key:
        return None
    try:
        from mem0 import MemoryClient

        return MemoryClient(api_key=settings.mem0_api_key)
    except Exception:
        logger.warning("mem0_client_init_failed")
        return None


async def store_vendor_correction_pattern(
    *,
    tenant_id: str,
    vendor_id: str,
    corrections: dict[str, Any],
    corrected_data: dict[str, Any],
) -> None:
    client = _get_mem0_client()
    if client is None:
        return

    correction_lines = [
        f"- {field}: corrected to {json.dumps(value, default=str)}"
        for field, value in corrections.items()
    ]
    content = (
        "Human corrected invoice extraction fields for this vendor.\n"
        + "\n".join(correction_lines)
        + f"\nFull corrected extraction:\n{json.dumps(corrected_data, default=str)}"
    )

    try:
        client.add(
            messages=[{"role": "user", "content": content}],
            user_id=_mem0_user_id(tenant_id, vendor_id),
            metadata={
                "type": "extraction_correction",
                "tenant_id": tenant_id,
                "vendor_id": vendor_id,
                "corrections": corrections,
            },
        )
        logger.info(
            "mem0_correction_stored",
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            fields=list(corrections.keys()),
        )
    except Exception:
        logger.exception("mem0_correction_store_failed", vendor_id=vendor_id)


async def fetch_vendor_correction_examples(
    tenant_id: str,
    vendor_id: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    client = _get_mem0_client()
    if client is None:
        return []

    try:
        results = client.search(
            query="invoice extraction correction examples for this vendor",
            user_id=_mem0_user_id(tenant_id, vendor_id),
            limit=limit,
        )
    except Exception:
        logger.warning("mem0_correction_fetch_failed", vendor_id=vendor_id)
        return []

    examples: list[dict[str, Any]] = []
    for item in results or []:
        metadata = item.get("metadata") or {}
        corrections = metadata.get("corrections")
        if corrections:
            examples.append(
                {
                    "corrections": corrections,
                    "memory": item.get("memory") or item.get("text") or "",
                }
            )
        elif item.get("memory"):
            examples.append({"memory": item.get("memory")})
    return examples
