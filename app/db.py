from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from app.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_key   TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL,
    content_type  TEXT NOT NULL DEFAULT 'application/octet-stream',
    size          INTEGER NOT NULL CHECK (size >= 0),
    sha256        TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at);
"""

SELECT_COLUMNS = (
    "id, storage_key, original_name, content_type, size, sha256, "
    "created_at, updated_at"
)


async def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(SCHEMA)
        await db.execute("PRAGMA journal_mode=WAL")


async def insert_file_record(
    db: aiosqlite.Connection,
    *,
    storage_key: str,
    original_name: str,
    content_type: str,
    size: int,
    sha256: str,
) -> dict[str, Any]:
    cursor = await db.execute(
        """
        INSERT INTO files (storage_key, original_name, content_type, size, sha256)
        VALUES (?, ?, ?, ?, ?)
        """,
        (storage_key, original_name, content_type, size, sha256),
    )
    await db.commit()
    return await get_file_record(db, cursor.lastrowid)


async def get_file_record(db: aiosqlite.Connection, file_id: int) -> dict[str, Any] | None:
    cursor = await db.execute(
        f"SELECT {SELECT_COLUMNS} FROM files WHERE id = ?",
        (file_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row is not None else None


async def list_file_records(
    db: aiosqlite.Connection,
    *,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if keyword:
        cursor = await db.execute(
            f"""
            SELECT {SELECT_COLUMNS} FROM files
            WHERE original_name LIKE ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (f"%{keyword}%", limit, offset),
        )
    else:
        cursor = await db.execute(
            f"""
            SELECT {SELECT_COLUMNS} FROM files
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def delete_file_record(db: aiosqlite.Connection, file_id: int) -> dict[str, Any] | None:
    record = await get_file_record(db, file_id)
    if record is None:
        return None
    await db.execute("DELETE FROM files WHERE id = ?", (file_id,))
    await db.commit()
    return record


async def _connect(db_path: Path) -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


@asynccontextmanager
async def db_session() -> AsyncIterator[aiosqlite.Connection]:
    db = await _connect(settings.db_path)
    try:
        yield db
    finally:
        await db.close()
