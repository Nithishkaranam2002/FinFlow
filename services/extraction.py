"""Document preparation utilities for vision-based invoice extraction."""

from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image

SUPPORTED_IMAGE_TYPES = {"png", "jpeg", "jpg", "webp", "tiff", "tif", "gif"}


class DocumentPreparationError(Exception):
    """Raised when a document cannot be prepared for vision extraction."""


def prepare_document_for_vision(file_bytes: bytes, file_type: str) -> tuple[bytes, str]:
    """
    Normalize uploaded documents into a vision-model-ready image.

    PDFs are converted to a PNG of the first page. Image files are validated
    and re-encoded to PNG for consistent downstream handling.

    Returns:
        (image_bytes, mime_type)
    """
    normalized_type = file_type.lower().strip().lstrip(".")
    if normalized_type == "pdf":
        return _pdf_first_page_to_png(file_bytes)
    if normalized_type in SUPPORTED_IMAGE_TYPES:
        return _normalize_image_bytes(file_bytes)
    raise DocumentPreparationError(f"Unsupported file type: {file_type}")


def encode_image_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _pdf_first_page_to_png(file_bytes: bytes) -> tuple[bytes, str]:
    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:
        raise DocumentPreparationError(
            "pdf2image is required for PDF extraction"
        ) from exc

    try:
        pages = convert_from_bytes(file_bytes, first_page=1, last_page=1, fmt="png")
    except Exception as exc:
        raise DocumentPreparationError(
            "Failed to convert PDF to image. Ensure poppler is installed."
        ) from exc

    if not pages:
        raise DocumentPreparationError("PDF contained no pages")

    buffer = io.BytesIO()
    pages[0].save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"


def _normalize_image_bytes(file_bytes: bytes) -> tuple[bytes, str]:
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue(), "image/png"
    except Exception as exc:
        raise DocumentPreparationError("Invalid or corrupted image file") from exc


async def extract_invoice(payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """
    Backward-compatible worker entrypoint.

    Delegates to the ingestion agent extraction pipeline when raw bytes are
    available; otherwise returns a minimal stub for legacy Kafka payloads.
    """
    from agents.ingestion_agent import extract_from_kafka_payload

    return await extract_from_kafka_payload(payload)
