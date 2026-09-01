"""Request-scoped trace id context for MDC-style logging."""

import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_var.get()


def generate_request_id() -> str:
    return uuid.uuid4().hex
