"""
Swimlanes submodule.

CUSTOM swimlanes are stored rows (Swimlane entity), created/renamed/
reordered/deleted just like columns. Every other strategy (ASSIGNEE,
PRIORITY, LABEL, PROJECT, EPIC) computes its groups dynamically at query
time from the underlying Task data (via TasksContextPort, the ACL to Tasks
& Work Management) — there is nothing to create or store for those.

EPIC grouping is accepted as a valid strategy value (the request lists it),
but there is no Epic concept anywhere in the platform yet — no bounded
context has ever defined one. Rather than fabricate a fake grouping, EPIC
returns a single honestly-labeled "No epics available" group containing
every card, so the API never silently misleads a caller into thinking
epics exist.
"""

from __future__ import annotations

from collections import defaultdict

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.boards.application.authorization_helpers import BoardAuthorization
from app.boards.application.dtos import SwimlaneDTO, SwimlaneGroupDTO
from app.boards.application.ports import OrgPermissionCheckerPort, ProjectContextPort, TasksContextPort
from app.boards.domain.entities import Swimlane, SwimlaneStrategy, compute_position_between
from app.boards.domain.events import SwimlaneCreated, SwimlaneDeleted, SwimlaneUpdated
from app.boards.domain.exceptions import BoardNotFoundError, CustomSwimlaneRequiredError, SwimlaneNotFoundError


def _to_dto(swimlane: Swimlane) -> SwimlaneDTO:
    return SwimlaneDTO(id=swimlane.id, board_id=swimlane.board_id, name=swimlane.name, position=swimlane.position)


class SwimlaneService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort, tasks_context: TasksContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = BoardAuthorization(permission_checker=permission_checker, project_context=project_context)
        self._tasks_context = tasks_context

    async def create_swimlane(self, *, board_id: EntityId, actor_user_id: UserId, name: str) -> SwimlaneDTO:
        async with self._uow_factory() as uow:
            board = await uow.boards.get_by_id(board_id)
            if board is None:
                raise BoardNotFoundError(board_id)
            await self._authorization.assert_can_manage(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)
            if board.swimlane_strategy != SwimlaneStrategy.CUSTOM:
                raise CustomSwimlaneRequiredError()

            existing = await uow.swimlanes.list_for_board(board_id)
            position = compute_position_between(existing[-1].position if existing else None, None)
            swimlane = Swimlane.create(board_id=board_id, name=name, position=position)
            await uow.swimlanes.add(swimlane)
            await uow.commit()
            await self._dispatcher.dispatch(SwimlaneCreated(aggregate_id=swimlane.id, board_id=board_id, name=name))
            return _to_dto(swimlane)

    async def list_for_board(self, *, board_id: EntityId) -> list[SwimlaneDTO]:
        async with self._uow_factory() as uow:
            swimlanes = await uow.swimlanes.list_for_board(board_id)
            return [_to_dto(s) for s in swimlanes]

    async def rename_swimlane(self, *, swimlane_id: EntityId, actor_user_id: UserId, name: str) -> SwimlaneDTO:
        async with self._uow_factory() as uow:
            swimlane = await uow.swimlanes.get_by_id(swimlane_id)
            if swimlane is None:
                raise SwimlaneNotFoundError(swimlane_id)
            board = await uow.boards.get_by_id(swimlane.board_id)
            await self._authorization.assert_can_manage(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            swimlane.rename(name)
            await uow.swimlanes.update(swimlane)
            await uow.commit()
            await self._dispatcher.dispatch(SwimlaneUpdated(aggregate_id=swimlane.id))
            return _to_dto(swimlane)

    async def reorder_swimlane(
        self, *, swimlane_id: EntityId, actor_user_id: UserId, previous_swimlane_id: EntityId | None,
        next_swimlane_id: EntityId | None,
    ) -> SwimlaneDTO:
        async with self._uow_factory() as uow:
            swimlane = await uow.swimlanes.get_by_id(swimlane_id)
            if swimlane is None:
                raise SwimlaneNotFoundError(swimlane_id)
            board = await uow.boards.get_by_id(swimlane.board_id)
            await self._authorization.assert_can_manage(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            previous_position = None
            if previous_swimlane_id is not None:
                previous = await uow.swimlanes.get_by_id(previous_swimlane_id)
                previous_position = previous.position if previous else None
            next_position = None
            if next_swimlane_id is not None:
                nxt = await uow.swimlanes.get_by_id(next_swimlane_id)
                next_position = nxt.position if nxt else None

            swimlane.set_position(compute_position_between(previous_position, next_position))
            await uow.swimlanes.update(swimlane)
            await uow.commit()
            return _to_dto(swimlane)

    async def delete_swimlane(self, *, swimlane_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            swimlane = await uow.swimlanes.get_by_id(swimlane_id)
            if swimlane is None:
                raise SwimlaneNotFoundError(swimlane_id)
            board = await uow.boards.get_by_id(swimlane.board_id)
            await self._authorization.assert_can_manage(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            await uow.swimlanes.delete(swimlane_id)
            await uow.commit()
            await self._dispatcher.dispatch(SwimlaneDeleted(aggregate_id=swimlane_id))

    async def compute_dynamic_groups(self, *, board_id: EntityId) -> list[SwimlaneGroupDTO]:
        """For ASSIGNEE/PRIORITY/LABEL/PROJECT/EPIC strategies — computed
        from Task data via the ACL, never stored."""
        async with self._uow_factory() as uow:
            board = await uow.boards.get_by_id(board_id)
            if board is None:
                raise BoardNotFoundError(board_id)
            cards = await uow.board_cards.list_for_board(board_id)
            strategy = board.swimlane_strategy

        if strategy == SwimlaneStrategy.EPIC:
            return [SwimlaneGroupDTO(key="no-epic", label="No epics available", card_ids=[c.id for c in cards])]

        if strategy == SwimlaneStrategy.PROJECT:
            groups: dict[str, list] = defaultdict(list)
            for card in cards:
                task = await self._tasks_context.get_task(task_id=card.task_id)
                key = str(task.project_id) if task else "unknown"
                groups[key].append(card.id)
            return [SwimlaneGroupDTO(key=k, label=k, card_ids=v) for k, v in groups.items()]

        if strategy == SwimlaneStrategy.PRIORITY:
            groups = defaultdict(list)
            for card in cards:
                task = await self._tasks_context.get_task(task_id=card.task_id)
                key = task.priority if task else "unknown"
                groups[key].append(card.id)
            return [SwimlaneGroupDTO(key=k, label=k.replace("_", " ").title(), card_ids=v) for k, v in groups.items()]

        if strategy == SwimlaneStrategy.ASSIGNEE:
            groups = defaultdict(list)
            for card in cards:
                assignee_ids = await self._tasks_context.list_assignee_ids(task_id=card.task_id)
                if not assignee_ids:
                    groups["unassigned"].append(card.id)
                for assignee_id in assignee_ids:
                    groups[str(assignee_id)].append(card.id)
            return [SwimlaneGroupDTO(key=k, label="Unassigned" if k == "unassigned" else k, card_ids=v) for k, v in groups.items()]

        if strategy == SwimlaneStrategy.LABEL:
            groups = defaultdict(list)
            for card in cards:
                label_ids = await self._tasks_context.list_label_ids(task_id=card.task_id)
                if not label_ids:
                    groups["unlabeled"].append(card.id)
                for label_id in label_ids:
                    groups[str(label_id)].append(card.id)
            return [SwimlaneGroupDTO(key=k, label="Unlabeled" if k == "unlabeled" else k, card_ids=v) for k, v in groups.items()]

        # NONE / CUSTOM: no dynamic grouping — CUSTOM uses stored Swimlane rows instead.
        return [SwimlaneGroupDTO(key="default", label="All Cards", card_ids=[c.id for c in cards])]
