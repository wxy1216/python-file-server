from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.errors import BizError, ErrorCode
from loguru import logger

EXCLUDED_PATHS = ("/docs", "/redoc", "/openapi.json")


class ApiMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith(EXCLUDED_PATHS):
            return await call_next(request)

        try:
            response = await call_next(request)
        except BizError as exc:
            return JSONResponse(
                {"code": exc.code, "msg": exc.msg, "data": exc.data},
                status_code=exc.http_status_code,
            )
        except Exception as exc:
            logger.opt(exception=exc).error(
                "unhandled exception: {} {}",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                {"code": ErrorCode.UNKNOWN, "msg": "system error", "data": None},
                status_code=500,
            )

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
