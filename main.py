from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api.health import router as health_router
from app.api.hello import router as hello_router
from app.api.demo import router as demo_router
from app.api.files import router as files_router
from app.config import settings
from app.db import init_db
from app.logging_config import setup_logging
from app.middleware import ApiMiddleware, TraceMiddleware
from app.storage import ensure_storage_dir

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    if not settings.api_token:
        logger.warning("API_TOKEN is not set; /api/files is unauthenticated")
    ensure_storage_dir()
    await init_db(settings.db_path)
    yield


app = FastAPI(
    title="Python File Server",
    description="A FastAPI-based file server scaffold.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(ApiMiddleware)
app.add_middleware(TraceMiddleware)
app.include_router(hello_router)
app.include_router(demo_router, prefix="/api/demo")
app.include_router(files_router)
app.include_router(health_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_config=None)
