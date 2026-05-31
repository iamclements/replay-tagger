from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure(level: str, fmt: str, silent: bool = False) -> None:
    """Configure structlog for either JSON (production) or pretty console (dev) output.

    Pass silent=True to suppress all log output (used by the doctor command).
    """
    if silent:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
            cache_logger_on_first_use=False,
        )
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if fmt == "text":
        processors = [*shared_processors, structlog.dev.ConsoleRenderer()]
    else:
        processors = [*shared_processors, structlog.processors.JSONRenderer()]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
