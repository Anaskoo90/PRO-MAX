"""
Job Monitoring: in-memory run history exposed for the health/observability
surface (a job that hasn't succeeded in N intervals is a readiness signal,
per the Observability module's health checks).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from app.platform_core.shared_kernel.utils import utcnow


@dataclass(frozen=True, slots=True)
class JobRunRecord:
    job_name: str
    started_at: datetime
    finished_at: datetime
    succeeded: bool
    error: str | None = None


class JobMonitor:
    def __init__(self, history_per_job: int = 20) -> None:
        self._history_per_job = history_per_job
        self._history: dict[str, deque[JobRunRecord]] = {}

    def record(self, run: JobRunRecord) -> None:
        history = self._history.setdefault(
            run.job_name, deque(maxlen=self._history_per_job)
        )
        history.append(run)

    def last_run(self, job_name: str) -> JobRunRecord | None:
        history = self._history.get(job_name)
        return history[-1] if history else None

    def is_healthy(self, job_name: str, *, max_consecutive_failures: int = 3) -> bool:
        history = self._history.get(job_name)
        if not history:
            return True
        recent = list(history)[-max_consecutive_failures:]
        return any(run.succeeded for run in recent)
