from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.hello import router as hello_router
from app.api.demo import router as demo_router
from app.logging_config import setup_logging
from app.middleware import ApiMiddleware

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    yield


app = FastAPI(
    title="Python File Server",
    description="A FastAPI-based file server scaffold.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(ApiMiddleware)
app.include_router(hello_router)
app.include_router(demo_router, prefix="/api/demo")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_config=None)
