from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")
