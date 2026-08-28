from fastapi import APIRouter

router = APIRouter()


@router.get("/api/hello")
async def hello() -> dict[str, str]:
    return {"message": "hello world"}
