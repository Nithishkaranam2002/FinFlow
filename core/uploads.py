"""Shared upload validation helpers."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

from core.config import get_settings


async def read_upload_with_limit(file: UploadFile) -> bytes:
    settings = get_settings()
    chunks: list[bytes] = []
    total = 0
    max_bytes = settings.max_upload_size_bytes

    while True:
        chunk = await file.read(1024 * 64)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum size of {max_bytes // (1024 * 1024)} MB",
            )
        chunks.append(chunk)

    return b"".join(chunks)
