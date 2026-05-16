from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure(level: str, fmt: str) -> None:
    """Configure structlog for either JSON (production) or pretty console (dev) output."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
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
