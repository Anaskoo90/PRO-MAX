"""
Structured logging, built on structlog, emitting JSON in production-like
profiles and a human-readable console renderer locally. Every log line
automatically carries correlation_id + bound log context + log level.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.platform_core.configuration.profiles import EnvironmentProfile
from app.platform_core.logging.context import get_log_context
from app.platform_core.logging.correlation import get_correlation_id


def _inject_correlation_id(logger, method_name, event_dict):
    correlation_id = get_correlation_id()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def _inject_log_context(logger, method_name, event_dict):
    event_dict.update(get_log_context())
    return event_dict


def configure_logging(environment: EnvironmentProfile, level: str = "INFO") -> None:
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_correlation_id,
        _inject_log_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if environment.is_production_like
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
