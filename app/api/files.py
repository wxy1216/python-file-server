from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Path, Query, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from starlette.responses import Response

from app.config import settings
from app.db import (
    db_session,
    delete_file_record,
    get_file_chunk_record,
    get_file_record,
    insert_file_with_chunks,
    list_file_chunk_records,
    list_file_records,
)
from app.errors import (
    ChunkNotFoundBizError,
    FileDataMissingError,
    FileNotFoundBizError,
)
from app.responses import SlicedFileResponse
from app.security import require_token
from app.storage import (
    delete_storage,
    resolve_chunk_path,
    resolve_storage_path,
    save_upload,
)

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
        chunks,
    ) = await save_upload(file)
    try:
        async with db_session() as db:
            return await insert_file_with_chunks(
                db,
                storage_key=storage_key,
                original_name=original_name,
                content_type=content_type,
                size=size,
                sha256=sha256,
                chunks=chunks,
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


@router.get("/{file_id}/chunks")
async def list_file_chunks(file_id: int) -> dict[str, Any]:
    async with db_session() as db:
        record = await get_file_record(db, file_id)
        if record is None:
            raise FileNotFoundBizError(data={"file_id": file_id})
        chunks = await list_file_chunk_records(db, file_id)
    return {
        "file_id": file_id,
        "total_size": record["size"],
        "chunk_size": settings.file_chunk_size,
        "chunks": [
            {
                "seq": chunk["seq"],
                "size": chunk["size"],
                "sha256": chunk["sha256"],
                "url": f"/api/files/{file_id}/chunks/{chunk['seq']}",
            }
            for chunk in chunks
        ],
    }


@router.get("/{file_id}/chunks/{seq}")
async def download_file_chunk(
    file_id: int,
    seq: int = Path(ge=1),
) -> FileResponse:
    async with db_session() as db:
        record = await get_file_record(db, file_id)
        if record is None:
            raise FileNotFoundBizError(data={"file_id": file_id})
        chunk = await get_file_chunk_record(db, file_id, seq)
    if chunk is None:
        raise ChunkNotFoundBizError(data={"file_id": file_id, "seq": seq})

    path = resolve_chunk_path(record["storage_key"], seq)
    if not path.is_file():
        logger.error(
            "chunk data missing: file_id={} seq={} path={}",
            file_id,
            seq,
            path,
        )
        raise FileDataMissingError(data={"file_id": file_id, "seq": seq})
    return FileResponse(path, media_type="application/octet-stream")


@router.api_route("/{file_id}/download", methods=["GET", "HEAD"])
async def download_file(file_id: int) -> Response:
    async with db_session() as db:
        record = await get_file_record(db, file_id)
        if record is None:
            raise FileNotFoundBizError(data={"file_id": file_id})
        chunks = await list_file_chunk_records(db, file_id)

    if chunks:
        chunk_paths = [
            (resolve_chunk_path(record["storage_key"], chunk["seq"]), chunk["size"])
            for chunk in chunks
        ]
        missing_paths = [
            str(path) for path, _ in chunk_paths if not path.is_file()
        ]
        if missing_paths:
            logger.error(
                "chunk data missing: file_id={} missing_paths={}",
                file_id,
                missing_paths,
            )
            raise FileDataMissingError(data={"file_id": file_id})
        return SlicedFileResponse(
            chunk_paths,
            media_type=record["content_type"],
            filename=record["original_name"],
            etag=f'"{record["sha256"]}"',
        )

    if record["size"] == 0:
        return SlicedFileResponse(
            [],
            media_type=record["content_type"],
            filename=record["original_name"],
            etag=f'"{record["sha256"]}"',
        )

    path = resolve_storage_path(record["storage_key"])
    if not path.is_file():
        logger.error("file data missing: storage_key={}", record["storage_key"])
        raise FileDataMissingError(data={"file_id": file_id})
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
