from __future__ import annotations

import logging
import sys

from loguru import logger
from app.trace import get_span_id, get_trace_id
from uvicorn.config import LOGGING_CONFIG as uvicorn_logging_config


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = sys._getframe(1)
        depth = 1
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "traceId=<cyan>{extra[traceId]}</cyan> "
    "spanId=<cyan>{extra[spanId]}</cyan> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)
FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "traceId={extra[traceId]} spanId={extra[spanId]} | "
    "{name}:{function}:{line} - {message}"
)


def setup_logging() -> None:
    logger.remove()
    logger.configure(
        extra={"traceId": "-", "spanId": "-"},
        patcher=lambda record: record["extra"].update(
            traceId=get_trace_id(),
            spanId=get_span_id(),
        ),
    )

    logger.add(
        sys.stdout,
        level="INFO",
        format=CONSOLE_FORMAT,
        backtrace=True,
        diagnose=False,
    )

    logger.add(
        "logs/app_info_{time:YYYY-MM-DD}.log",
        level="INFO",
        format=FILE_FORMAT,
        rotation="1 day",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        watch=True,
    )

    logger.add(
        "logs/app_wf_{time:YYYY-MM-DD}.log",
        level="WARNING",
        format=FILE_FORMAT,
        rotation="1 day",
        retention="90 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        watch=True,
    )

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(name)
        log.handlers = [InterceptHandler()]
        log.propagate = False
        log.setLevel(logging.INFO)

    # Uvicorn CLI re-applies its default logging config at startup, which would
    # wipe the handlers above. Point those handlers at loguru as well.
    uvicorn_logging_config["handlers"]["default"] = {"()": InterceptHandler}
    uvicorn_logging_config["handlers"]["access"] = {"()": InterceptHandler}
