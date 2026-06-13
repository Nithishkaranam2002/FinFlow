import io

import pytest
from fastapi import HTTPException, UploadFile

from core.config import get_settings
from core.uploads import read_upload_with_limit


@pytest.mark.asyncio
async def test_rejects_files_above_configured_limit(monkeypatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "1024")
    get_settings.cache_clear()

    upload = UploadFile(filename="large.pdf", file=io.BytesIO(b"x" * 2048))

    with pytest.raises(HTTPException) as exc:
        await read_upload_with_limit(upload)

    assert exc.value.status_code == 413

@pytest.mark.asyncio
async def test_accepts_files_within_limit(monkeypatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "4096")
    get_settings.cache_clear()

    payload = b"small-pdf-content"
    upload = UploadFile(filename="small.pdf", file=io.BytesIO(payload))

    assert await read_upload_with_limit(upload) == payload
