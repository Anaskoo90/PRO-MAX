"""Tasks & Work Management specifications, per the Domain Modeling & DDD
Blueprint's Specification pattern (shared_kernel.validation.Specification)."""

from __future__ import annotations

from datetime import datetime

from app.platform_core.shared_kernel.utils import utcnow
from app.platform_core.shared_kernel.validation import Specification
from app.tasks.domain.entities import Task
from app.tasks.domain.workflow import TERMINAL_STATUSES


class TaskIsOverdueSpecification(Specification[Task]):
    def __init__(self, *, now: datetime | None = None) -> None:
        self._now = now or utcnow()

    def is_satisfied_by(self, candidate: Task) -> bool:
        return candidate.is_overdue(now=self._now)


class TaskIsActiveSpecification(Specification[Task]):
    """Not archived, not soft-deleted, not in a terminal workflow status —
    the definition of "still in flight" used by default task listings."""

    def is_satisfied_by(self, candidate: Task) -> bool:
        return not candidate.is_archived and candidate.deleted_at is None and candidate.status not in TERMINAL_STATUSES
