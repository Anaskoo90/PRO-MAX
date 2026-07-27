"""Background Job Logging: a decorator giving every job run a structured
start/success/failure log line and its own correlation id, since jobs run
outside any HTTP request context."""

from __future__ import annotations

import functools
import time
from typing import Awaitable, Callable, TypeVar

from app.platform_core.logging.context import bind_log_context
from app.platform_core.logging.correlation import new_correlation_id, set_correlation_id
from app.platform_core.logging.logger import get_logger

_logger = get_logger("jobs")

T = TypeVar("T")


def log_job_execution(job_name: str) -> Callable[
    [Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]
]:
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            set_correlation_id(new_correlation_id())
            with bind_log_context(job_name=job_name):
                start = time.perf_counter()
                await _logger.ainfo("job_started")
                try:
                    result = await func(*args, **kwargs)
                except Exception:
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    await _logger.aerror("job_failed", duration_ms=duration_ms, exc_info=True)
                    raise
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                await _logger.ainfo("job_succeeded", duration_ms=duration_ms)
                return result

        return wrapper

    return decorator
