from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from loguru import logger

from app.db import (
    db_session,
    delete_file_record,
    get_file_record,
    insert_file_record,
    list_file_records,
)
from app.errors import FileNotFoundBizError
from app.security import require_token
from app.storage import delete_storage, resolve_storage_path, save_upload

router = APIRouter(
    prefix="/api/files",
    tags=["files"],
    dependencies=[Depends(require_token)],
)


@router.post("", status_code=201)
async def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    (
        storage_key,
        original_name,
        content_type,
        size,
        sha256,
    ) = await save_upload(file)
    try:
        async with db_session() as db:
            return await insert_file_record(
                db,
                storage_key=storage_key,
                original_name=original_name,
                content_type=content_type,
                size=size,
                sha256=sha256,
            )
    except Exception:
        await delete_storage(storage_key)
        raise


@router.get("")
async def list_files(
    keyword: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    async with db_session() as db:
        records = await list_file_records(
            db,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
    return {"items": records, "limit": limit, "offset": offset}


@router.get("/{file_id}")
async def get_file(file_id: int) -> dict[str, Any]:
    async with db_session() as db:
        record = await get_file_record(db, file_id)
    if record is None:
        raise FileNotFoundBizError(data={"file_id": file_id})
    return record


@router.get("/{file_id}/download")
async def download_file(file_id: int) -> FileResponse:
    async with db_session() as db:
        record = await get_file_record(db, file_id)
    if record is None:
        raise FileNotFoundBizError(data={"file_id": file_id})

    path = resolve_storage_path(record["storage_key"])
    if not path.is_file():
        logger.error("file data missing: storage_key={}", record["storage_key"])
        raise RuntimeError("file data missing")

    return FileResponse(
        path,
        filename=record["original_name"],
        media_type=record["content_type"],
    )


@router.delete("/{file_id}")
async def delete_file(file_id: int) -> dict[str, Any]:
    async with db_session() as db:
        record = await delete_file_record(db, file_id)
    if record is None:
        raise FileNotFoundBizError(data={"file_id": file_id})
    await delete_storage(record["storage_key"])
    return {"deleted": True, "file_id": file_id}
