"""Job-level retry, reusing the Messaging Foundation's RetryPolicy so
jobs and message consumers share one backoff algorithm."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

from app.platform_core.logging.logger import get_logger
from app.platform_core.messaging.retry_policy import DEFAULT_RETRY_POLICY, RetryPolicy

T = TypeVar("T")

_logger = get_logger("jobs.retry")


async def run_with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> T:
    attempt = 0
    while True:
        attempt += 1
        try:
            return await func()
        except Exception:
            if not policy.should_retry(attempt):
                await _logger.aerror("job_retry_exhausted", attempt=attempt, exc_info=True)
                raise
            delay = policy.delay_for_attempt(attempt)
            await _logger.awarn("job_retrying", attempt=attempt, delay_seconds=delay)
            await asyncio.sleep(delay)
