"""B3 trace context for MDC-style distributed tracing."""

import re
import uuid
from contextvars import ContextVar

DEFAULT_ID = "-"
TRACE_ID_LENGTH = 32
SPAN_ID_LENGTH = 16

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")

trace_id_var: ContextVar[str] = ContextVar("trace_id", default=DEFAULT_ID)
span_id_var: ContextVar[str] = ContextVar("span_id", default=DEFAULT_ID)
parent_span_id_var: ContextVar[str | None] = ContextVar("parent_span_id", default=None)


def get_trace_id() -> str:
    return trace_id_var.get()


def get_span_id() -> str:
    return span_id_var.get()


def get_parent_span_id() -> str | None:
    return parent_span_id_var.get()


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def generate_span_id() -> str:
    return uuid.uuid4().hex[:SPAN_ID_LENGTH]


def normalize_trace_id(value: str | None) -> str | None:
    if value is not None and _valid_hex(value, TRACE_ID_LENGTH):
        return value.lower()
    return None


def normalize_span_id(value: str | None) -> str | None:
    if value is not None and _valid_hex(value, SPAN_ID_LENGTH):
        return value.lower()
    return None


def set_context(
    trace_id: str,
    span_id: str,
    parent_span_id: str | None = None,
) -> None:
    trace_id_var.set(trace_id)
    span_id_var.set(span_id)
    parent_span_id_var.set(parent_span_id)


def _valid_hex(value: str, length: int) -> bool:
    return len(value) == length and _HEX_RE.fullmatch(value) is not None
