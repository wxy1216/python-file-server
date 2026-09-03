from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from anyio import open_file, to_thread
from fastapi import UploadFile
from loguru import logger

from app.config import settings
from app.errors import FileTooLargeError

READ_CHUNK_SIZE = 1024 * 1024


def ensure_storage_dir() -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str | None) -> str:
    if not name:
        return "upload"
    cleaned = Path(name.replace("\\", "/")).name.strip()
    cleaned = "".join(char for char in cleaned if char not in "\x00\r\n")
    return cleaned or "upload"


def chunk_filename(seq: int) -> str:
    return f"{seq:08d}.part"


def resolve_chunk_path(storage_key: str, seq: int) -> Path:
    if seq < 1:
        raise ValueError("chunk seq must be positive")
    return resolve_storage_path(storage_key) / chunk_filename(seq)


async def save_upload(
    upload: UploadFile,
) -> tuple[str, str, str, int, str, list[tuple[int, int, str]]]:
    ensure_storage_dir()

    storage_key = uuid.uuid4().hex
    final_dir = resolve_storage_path(storage_key)
    temp_dir = settings.storage_dir / f".{storage_key}.tmp"
    original_name = sanitize_filename(upload.filename)
    content_type = upload.content_type or "application/octet-stream"
    digest = hashlib.sha256()
    total = 0
    chunks: list[tuple[int, int, str]] = []

    try:
        temp_dir.mkdir(parents=True)
        seq = 1
        while True:
            chunk_path = temp_dir / chunk_filename(seq)
            chunk_digest = hashlib.sha256()
            chunk_size = 0
            remaining = settings.file_chunk_size
            async with await open_file(chunk_path, "wb") as dest:
                while remaining > 0:
                    chunk = await upload.read(min(READ_CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > settings.max_upload_size:
                        raise FileTooLargeError(
                            data={"max_upload_size": settings.max_upload_size}
                        )
                    digest.update(chunk)
                    chunk_digest.update(chunk)
                    await dest.write(chunk)
                    chunk_size += len(chunk)
                    remaining -= len(chunk)

            if chunk_size == 0:
                chunk_path.unlink(missing_ok=True)
                break
            chunks.append((seq, chunk_size, chunk_digest.hexdigest()))
            seq += 1
            if chunk_size < settings.file_chunk_size:
                break

        if chunks:
            temp_dir.replace(final_dir)
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(final_dir, ignore_errors=True)
        raise
    finally:
        await upload.close()

    return storage_key, original_name, content_type, total, digest.hexdigest(), chunks


def resolve_storage_path(storage_key: str) -> Path:
    if Path(storage_key).name != storage_key:
        raise ValueError("invalid storage key")
    return settings.storage_dir / storage_key


def _remove_storage_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


async def delete_storage(storage_key: str) -> None:
    path = resolve_storage_path(storage_key)
    try:
        await to_thread.run_sync(_remove_storage_path, path)
    except OSError as exc:
        logger.warning(
            "failed to delete file data: storage_key={} error={}",
            storage_key,
            exc,
        )
