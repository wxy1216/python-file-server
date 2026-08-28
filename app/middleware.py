from __future__ import annotations

import json
import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.errors import BizError, ErrorCode

EXCLUDED_PATHS = ("/docs", "/redoc", "/openapi.json")

logger = logging.getLogger(__name__)


class ResponseWrapperMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith(EXCLUDED_PATHS):
            return await call_next(request)

        response = await call_next(request)
        if response.status_code == 204:
            return response
        if not 200 <= response.status_code < 300:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        return JSONResponse(
            {"code": 0, "msg": "success", "data": self._parse_body(body)},
            status_code=response.status_code,
        )

    @staticmethod
    def _parse_body(body: bytes) -> Any:
        if not body:
            return None
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return body.decode("utf-8", errors="replace")


class CustomExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except BizError as exc:
            return JSONResponse(
                {"code": exc.code, "msg": exc.msg, "data": exc.data},
                status_code=exc.http_status_code,
            )


class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception:
            logger.exception("unhandled exception")
            return JSONResponse(
                {"code": ErrorCode.UNKNOWN, "msg": "system error", "data": None},
                status_code=500,
            )
