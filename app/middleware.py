from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.errors import BizError, ErrorCode, SvcError
from app.trace import (
    generate_span_id,
    generate_trace_id,
    normalize_span_id,
    normalize_trace_id,
    set_context,
)
from loguru import logger

EXCLUDED_PATHS = ("/docs", "/redoc", "/openapi.json")


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = normalize_trace_id(
            request.headers.get("X-B3-TraceId")
        ) or generate_trace_id()
        parent_span_id = normalize_span_id(request.headers.get("X-B3-SpanId"))
        span_id = generate_span_id()
        set_context(trace_id, span_id, parent_span_id)
        response = await call_next(request)
        response.headers["X-B3-TraceId"] = trace_id
        response.headers["X-B3-SpanId"] = span_id
        return response


class ApiMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith(EXCLUDED_PATHS):
            return await call_next(request)

        try:
            response = await call_next(request)
        except BizError as exc:
            logger.opt(exception=exc).warning(
                "biz error: {} {} code={} msg={}",
                request.method,
                request.url.path,
                exc.code,
                exc.msg,
            )
            return JSONResponse(
                {"code": exc.code, "msg": exc.msg, "data": exc.data},
                status_code=exc.http_status_code,
            )
        except SvcError as exc:
            logger.opt(exception=exc).error(
                "service error: {} {} code={} msg={}",
                request.method,
                request.url.path,
                exc.code,
                exc.msg,
            )
            return JSONResponse(
                {"code": exc.code, "msg": "internal server error", "data": None},
                status_code=500,
            )
        except Exception as exc:
            logger.opt(exception=exc).error(
                "unhandled exception: {} {}",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                {"code": ErrorCode.UNKNOWN, "msg": "internal server error", "data": None},
                status_code=500,
            )

        # File downloads and non-JSON responses must stay untouched so the
        # body can stream to the client instead of being buffered and wrapped.
        content_type = response.headers.get("content-type", "")
        if response.headers.get("content-disposition") or not content_type.startswith(
            "application/json"
        ):
            return response

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
