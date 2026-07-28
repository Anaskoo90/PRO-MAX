"""
Sprint Management submodule (continued): burn-down.

A genuine day-by-day burndown needs historical data points, which needs
something to take a snapshot each day — `record_daily_snapshots` is that
job body, run by Platform Core's JobScheduler (see composition.py, the
same reuse Tasks & Work Management already established for its overdue-
scan job). It's idempotent per (sprint, day): re-running it the same day
is a no-op. `get_burndown` is the read side: actual remaining-work
snapshots plus a straight-line "ideal" burn computed from capacity and the
sprint's date range.
"""

from __future__ import annotations

from datetime import date

from app.platform_core.logging.logger import get_logger
from app.platform_core.shared_kernel.types import EntityId
from app.boards.application.dtos import BurndownReportDTO, BurndownSnapshotDTO
from app.boards.application.ports import TasksContextPort
from app.boards.domain.entities import EstimateType, Sprint, SprintBurndownSnapshot
from app.boards.domain.exceptions import SprintNotFoundError

_logger = get_logger("boards.sprint_reporting")

# Plain string literals matching Tasks & Work Management's TaskStatus
# values (via TasksContextPort.TaskSummary.status, a plain str) — Boards
# deliberately does not import Tasks' TaskStatus enum here, keeping the
# ACL boundary a matter of strings, not shared types.
_TERMINAL_TASK_STATUSES = frozenset({"done", "cancelled"})


class SprintReportingService:
    def __init__(self, *, uow_factory, tasks_context: TasksContextPort) -> None:
        self._uow_factory = uow_factory
        self._tasks_context = tasks_context

    async def _remaining_estimate_for_sprint(self, uow, sprint: Sprint) -> tuple[float, float]:
        cards = await uow.board_cards.list_for_sprint(sprint.id)
        remaining_points = 0.0
        remaining_hours = 0.0
        for card in cards:
            if card.estimate_value is None:
                continue
            task = await self._tasks_context.get_task(task_id=card.task_id)
            if task is not None and task.status in _TERMINAL_TASK_STATUSES:
                continue
            if card.estimate_type == EstimateType.STORY_POINTS:
                remaining_points += card.estimate_value
            elif card.estimate_type == EstimateType.HOURS:
                remaining_hours += card.estimate_value
        return remaining_points, remaining_hours

    async def record_daily_snapshots(self) -> int:
        """Job body: one snapshot per currently-ACTIVE sprint, per day.
        Returns the count of snapshots actually written (0 if today's
        snapshot already existed for every active sprint)."""
        today = date.today()
        written = 0
        async with self._uow_factory() as uow:
            active_sprints = await uow.sprints.list_all_active()
            for sprint in active_sprints:
                if await uow.sprint_burndown_snapshots.get_for_day(sprint.id, today) is not None:
                    continue
                remaining_points, remaining_hours = await self._remaining_estimate_for_sprint(uow, sprint)
                snapshot = SprintBurndownSnapshot.create(
                    sprint_id=sprint.id, snapshot_date=today, remaining_points=remaining_points, remaining_hours=remaining_hours,
                )
                await uow.sprint_burndown_snapshots.add(snapshot)
                written += 1
            await uow.commit()
        return written

    async def get_burndown(self, *, sprint_id: EntityId) -> BurndownReportDTO:
        async with self._uow_factory() as uow:
            sprint = await uow.sprints.get_by_id(sprint_id)
            if sprint is None:
                raise SprintNotFoundError(sprint_id)
            snapshots = await uow.sprint_burndown_snapshots.list_for_sprint(sprint_id)

        ideal_line: list[float] = []
        if sprint.start_date is not None and sprint.end_date is not None and sprint.capacity is not None:
            total_days = max((sprint.end_date - sprint.start_date).days, 1)
            for day_offset in range(total_days + 1):
                fraction_remaining = max(0.0, 1 - (day_offset / total_days))
                ideal_line.append(round(sprint.capacity * fraction_remaining, 2))

        return BurndownReportDTO(
            sprint_id=sprint.id, capacity=sprint.capacity,
            snapshots=[BurndownSnapshotDTO(snapshot_date=s.snapshot_date, remaining_points=s.remaining_points, remaining_hours=s.remaining_hours) for s in snapshots],
            ideal_remaining_by_day=ideal_line,
        )
