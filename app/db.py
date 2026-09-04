from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.models import FileChunkRecord, FileRecord

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _file_to_dict(file: FileRecord) -> dict[str, Any]:
    return {
        "id": file.id,
        "storage_key": file.storage_key,
        "original_name": file.original_name,
        "content_type": file.content_type,
        "size": file.size,
        "sha256": file.sha256,
        "created_at": _format_datetime(file.created_at),
        "updated_at": _format_datetime(file.updated_at),
    }


def _chunk_to_dict(chunk: FileChunkRecord) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "file_id": chunk.file_id,
        "seq": chunk.seq,
        "size": chunk.size,
        "sha256": chunk.sha256,
        "created_at": _format_datetime(chunk.created_at),
    }


async def init_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        return
    _engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
    )


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        await init_db()
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session


async def insert_file_with_chunks(
    db: AsyncSession,
    *,
    storage_key: str,
    original_name: str,
    content_type: str,
    size: int,
    sha256: str,
    chunks: list[tuple[int, int, str]],
) -> dict[str, Any]:
    file = FileRecord(
        storage_key=storage_key,
        original_name=original_name,
        content_type=content_type,
        size=size,
        sha256=sha256,
    )
    try:
        db.add(file)
        await db.flush()
        for seq, chunk_size, chunk_sha256 in chunks:
            db.add(
                FileChunkRecord(
                    file_id=file.id,
                    seq=seq,
                    size=chunk_size,
                    sha256=chunk_sha256,
                )
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(file)
    return _file_to_dict(file)


async def get_file_record(
    db: AsyncSession,
    file_id: int,
) -> dict[str, Any] | None:
    file = await db.get(FileRecord, file_id)
    if file is None:
        return None
    return _file_to_dict(file)


async def list_file_chunk_records(
    db: AsyncSession,
    file_id: int,
) -> list[dict[str, Any]]:
    result = await db.scalars(
        select(FileChunkRecord)
        .where(FileChunkRecord.file_id == file_id)
        .order_by(FileChunkRecord.seq)
    )
    return [_chunk_to_dict(chunk) for chunk in result.all()]


async def get_file_chunk_record(
    db: AsyncSession,
    file_id: int,
    seq: int,
) -> dict[str, Any] | None:
    result = await db.scalars(
        select(FileChunkRecord).where(
            FileChunkRecord.file_id == file_id,
            FileChunkRecord.seq == seq,
        )
    )
    chunk = result.first()
    if chunk is None:
        return None
    return _chunk_to_dict(chunk)


async def list_file_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    statement = select(FileRecord).order_by(FileRecord.id.desc())
    if keyword:
        statement = statement.where(
            FileRecord.original_name.like(f"%{keyword}%")
        )
    result = await db.scalars(
        statement.limit(limit).offset(offset)
    )
    return [_file_to_dict(file) for file in result.all()]


async def delete_file_record(
    db: AsyncSession,
    file_id: int,
) -> dict[str, Any] | None:
    file = await db.get(FileRecord, file_id)
    if file is None:
        return None
    record = _file_to_dict(file)
    try:
        await db.execute(
            delete(FileChunkRecord).where(FileChunkRecord.file_id == file_id)
        )
        await db.delete(file)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return record
