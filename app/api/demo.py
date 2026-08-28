from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.errors import (
    AccountDisabledError,
    FileNotFoundBizError,
    NotLoggedInError,
)

router = APIRouter()


class FileCreate(BaseModel):
    name: str
    size: int = Field(gt=0)


class FileUpdate(BaseModel):
    name: str | None = None
    size: int | None = Field(default=None, gt=0)


DEMO_FILES = [
    {"id": 1, "name": "readme.md", "size": 1024},
    {"id": 2, "name": "main.py", "size": 2048},
]


@router.get("/files")
async def list_files(keyword: str | None = Query(default=None)) -> list[dict[str, int | str]]:
    if keyword:
        lowered = keyword.lower()
        return [file for file in DEMO_FILES if lowered in file["name"].lower()]
    return DEMO_FILES


@router.get("/files/{file_id}")
async def get_file(file_id: int) -> dict[str, int | str]:
    for file in DEMO_FILES:
        if file["id"] == file_id:
            return file
    raise FileNotFoundBizError(data={"file_id": file_id})


@router.post("/files", status_code=201)
async def create_file(payload: FileCreate) -> dict[str, int | str]:
    next_id = max((file["id"] for file in DEMO_FILES), default=0) + 1
    file = {"id": next_id, "name": payload.name, "size": payload.size}
    DEMO_FILES.append(file)
    return file


@router.put("/files/{file_id}")
async def update_file(file_id: int, payload: FileUpdate) -> dict[str, int | str]:
    for file in DEMO_FILES:
        if file["id"] == file_id:
            if payload.name is not None:
                file["name"] = payload.name
            if payload.size is not None:
                file["size"] = payload.size
            return file
    raise FileNotFoundBizError(data={"file_id": file_id})


@router.delete("/files/{file_id}")
async def delete_file(file_id: int) -> dict[str, int | bool]:
    for index, file in enumerate(DEMO_FILES):
        if file["id"] == file_id:
            DEMO_FILES.pop(index)
            return {"deleted": True, "file_id": file_id}
    raise FileNotFoundBizError(data={"file_id": file_id})


@router.get("/auth/not-logged-in")
async def demo_not_logged_in() -> None:
    raise NotLoggedInError()


@router.get("/auth/account-disabled")
async def demo_account_disabled() -> None:
    raise AccountDisabledError()


@router.get("/error/unknown")
async def demo_unknown_error() -> None:
    raise RuntimeError("demo unexpected error")
