from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from anyio import open_file, to_thread
from fastapi import UploadFile
from loguru import logger

from app.config import settings
from app.errors import FileTooLargeError

CHUNK_SIZE = 1024 * 1024


def ensure_storage_dir() -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str | None) -> str:
    if not name:
        return "upload"
    cleaned = Path(name.replace("\\", "/")).name.strip()
    cleaned = "".join(char for char in cleaned if char not in "\x00\r\n")
    return cleaned or "upload"


async def save_upload(upload: UploadFile) -> tuple[str, str, str, int, str]:
    ensure_storage_dir()

    storage_key = uuid.uuid4().hex
    final_path = settings.storage_dir / storage_key
    temp_path = settings.storage_dir / f".{storage_key}.tmp"
    original_name = sanitize_filename(upload.filename)
    content_type = upload.content_type or "application/octet-stream"
    digest = hashlib.sha256()
    total = 0

    try:
        async with await open_file(temp_path, "wb") as dest:
            while chunk := await upload.read(CHUNK_SIZE):
                total += len(chunk)
                if total > settings.max_upload_size:
                    raise FileTooLargeError(
                        data={"max_upload_size": settings.max_upload_size}
                    )
                digest.update(chunk)
                await dest.write(chunk)
        temp_path.replace(final_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return storage_key, original_name, content_type, total, digest.hexdigest()


def resolve_storage_path(storage_key: str) -> Path:
    if Path(storage_key).name != storage_key:
        raise ValueError("invalid storage key")
    return settings.storage_dir / storage_key


async def delete_storage(storage_key: str) -> None:
    path = resolve_storage_path(storage_key)
    try:
        await to_thread.run_sync(lambda: path.unlink(missing_ok=True))
    except OSError as exc:
        logger.warning(
            "failed to delete file data: storage_key={} error={}",
            storage_key,
            exc,
        )
