"""
Job Scheduler: recurring and one-off job registration. This is an
interface + in-process implementation suitable for a single-worker
deployment; the Deployment Specification's multi-replica worker pool
implementation swaps this for a distributed scheduler (still an open
infra choice) without changing JobDefinition or JobExecutor.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.platform_core.logging.logger import get_logger

_logger = get_logger("jobs.scheduler")

JobFunc = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class JobDefinition:
    name: str
    func: JobFunc
    interval_seconds: float | None = None
    """None means the job is one-off, triggered explicitly rather than on a timer."""


class JobScheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, JobDefinition] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def register(self, job: JobDefinition) -> None:
        self._jobs[job.name] = job

    async def start(self) -> None:
        for job in self._jobs.values():
            if job.interval_seconds is not None:
                self._tasks[job.name] = asyncio.create_task(
                    self._run_recurring(job), name=f"scheduler:{job.name}"
                )

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def trigger_now(self, job_name: str) -> None:
        job = self._jobs[job_name]
        await job.func()

    async def _run_recurring(self, job: JobDefinition) -> None:
        assert job.interval_seconds is not None
        while True:
            try:
                await job.func()
            except asyncio.CancelledError:
                raise
            except Exception:
                await _logger.aerror("scheduled_job_failed", job_name=job.name, exc_info=True)
            await asyncio.sleep(job.interval_seconds)
