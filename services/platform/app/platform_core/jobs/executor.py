"""
Job Executor: runs a single job invocation with structured logging
(platform_core.logging.job_logging), timeout enforcement, and cancellation
support — the unit JobScheduler.trigger_now and message consumers both use
to actually run a job body, rather than calling job.func() bare.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

from app.platform_core.logging.job_logging import log_job_execution
from app.platform_core.shared_kernel.constants import TIMEOUT_EXTERNAL_SECONDS

T = TypeVar("T")


class JobExecutor:
    def __init__(self, default_timeout_seconds: float = TIMEOUT_EXTERNAL_SECONDS) -> None:
        self._default_timeout_seconds = default_timeout_seconds

    async def run(
        self,
        job_name: str,
        func: Callable[[], Awaitable[T]],
        *,
        timeout_seconds: float | None = None,
    ) -> T:
        @log_job_execution(job_name)
        async def _execute() -> T:
            return await asyncio.wait_for(
                func(), timeout=timeout_seconds or self._default_timeout_seconds
            )

        return await _execute()
