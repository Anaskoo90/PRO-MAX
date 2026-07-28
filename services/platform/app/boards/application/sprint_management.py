"""Sprint Management submodule: create, start, complete, cancel sprints;
track goal, capacity, velocity."""

from __future__ import annotations

from datetime import date

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.boards.application.authorization_helpers import BoardAuthorization
from app.boards.application.dtos import SprintDTO
from app.boards.application.ports import OrgPermissionCheckerPort, ProjectContextPort, TasksContextPort
from app.boards.domain.audit import BoardsAuditEventCategory, BoardsAuditLogRecord
from app.boards.domain.entities import Sprint
from app.boards.domain.exceptions import BoardNotFoundError, OnlyOneActiveSprintPerBoardError, SprintNotFoundError


def _to_dto(sprint: Sprint) -> SprintDTO:
    return SprintDTO(
        id=sprint.id, board_id=sprint.board_id, name=sprint.name, goal=sprint.goal, status=sprint.status.value,
        start_date=sprint.start_date, end_date=sprint.end_date, capacity=sprint.capacity,
    )


class SprintService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort, tasks_context: TasksContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = BoardAuthorization(permission_checker=permission_checker, project_context=project_context)
        self._tasks_context = tasks_context

    async def create_sprint(
        self, *, board_id: EntityId, actor_user_id: UserId, name: str, goal: str = "",
        start_date: date | None = None, end_date: date | None = None, capacity: float | None = None,
    ) -> SprintDTO:
        async with self._uow_factory() as uow:
            board = await uow.boards.get_by_id(board_id)
            if board is None:
                raise BoardNotFoundError(board_id)
            await self._authorization.assert_can_manage_sprint(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            sprint = Sprint.create(board_id=board_id, name=name, goal=goal, start_date=start_date, end_date=end_date, capacity=capacity)
            await uow.sprints.add(sprint)
            events = sprint.pull_domain_events()
            await uow.audit_logs.add(
                BoardsAuditLogRecord.create(
                    org_id=board.org_id, category=BoardsAuditEventCategory.SPRINT_CHANGE, action="sprint_created",
                    actor_user_id=actor_user_id, resource_type="sprint", resource_id=str(sprint.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(sprint)

    async def get(self, *, sprint_id: EntityId) -> SprintDTO:
        async with self._uow_factory() as uow:
            sprint = await uow.sprints.get_by_id(sprint_id)
            if sprint is None:
                raise SprintNotFoundError(sprint_id)
            return _to_dto(sprint)

    async def list_for_board(self, *, board_id: EntityId) -> list[SprintDTO]:
        async with self._uow_factory() as uow:
            sprints = await uow.sprints.list_for_board(board_id)
            return [_to_dto(s) for s in sprints]

    async def update(
        self, *, sprint_id: EntityId, actor_user_id: UserId, name: str | None = None, goal: str | None = None,
        start_date: date | None = None, end_date: date | None = None, capacity: float | None = None,
    ) -> SprintDTO:
        async with self._uow_factory() as uow:
            sprint = await self._load_and_authorize(uow, sprint_id=sprint_id, actor_user_id=actor_user_id)
            sprint.update(name=name, goal=goal, start_date=start_date, end_date=end_date, capacity=capacity)
            await uow.sprints.update(sprint)
            events = sprint.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(sprint)

    async def _load_and_authorize(self, uow, *, sprint_id: EntityId, actor_user_id: UserId) -> Sprint:
        sprint = await uow.sprints.get_by_id(sprint_id)
        if sprint is None:
            raise SprintNotFoundError(sprint_id)
        board = await uow.boards.get_by_id(sprint.board_id)
        if board is None:
            raise BoardNotFoundError(sprint.board_id)
        await self._authorization.assert_can_manage_sprint(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)
        return sprint

    async def start_sprint(self, *, sprint_id: EntityId, actor_user_id: UserId) -> SprintDTO:
        async with self._uow_factory() as uow:
            sprint = await self._load_and_authorize(uow, sprint_id=sprint_id, actor_user_id=actor_user_id)
            active = await uow.sprints.get_active_for_board(sprint.board_id)
            if active is not None and active.id != sprint.id:
                raise OnlyOneActiveSprintPerBoardError()

            sprint.start()
            await uow.sprints.update(sprint)
            events = sprint.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(sprint)

    async def complete_sprint(self, *, sprint_id: EntityId, actor_user_id: UserId) -> SprintDTO:
        async with self._uow_factory() as uow:
            sprint = await self._load_and_authorize(uow, sprint_id=sprint_id, actor_user_id=actor_user_id)
            sprint.complete()
            await uow.sprints.update(sprint)
            events = sprint.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(sprint)

    async def cancel_sprint(self, *, sprint_id: EntityId, actor_user_id: UserId) -> SprintDTO:
        async with self._uow_factory() as uow:
            sprint = await self._load_and_authorize(uow, sprint_id=sprint_id, actor_user_id=actor_user_id)
            sprint.cancel()
            await uow.sprints.update(sprint)
            events = sprint.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(sprint)

    async def get_velocity(self, *, sprint_id: EntityId) -> float:
        """Velocity: sum of story-point estimates for cards in this sprint
        whose underlying task has actually reached 'done' — computed
        on demand rather than stored, since it only has a stable meaning
        once the sprint is complete (a running total mid-sprint is really
        "points completed so far", which this same computation also
        answers correctly)."""
        async with self._uow_factory() as uow:
            cards = await uow.board_cards.list_for_sprint(sprint_id)

        total = 0.0
        for card in cards:
            if card.estimate_type != "story_points" or card.estimate_value is None:
                continue
            task = await self._tasks_context.get_task(task_id=card.task_id)
            if task is not None and task.status == "done":
                total += card.estimate_value
        return total
