"""
Task Movement submodule: move task between columns, reorder tasks, drag &
drop, batch move. Fractional-indexing position (compute_position_between)
keeps ordering consistent the same way Tasks' own drag-and-drop does — only
the moved card's position is ever rewritten.

Moving a card into a column with a `mapped_task_status` reuses Tasks'
own TaskLifecycleService (via TasksContextPort) to keep the underlying
task's real status in sync with its visual column — WIP limits are
enforced here, before that sync happens, so a rejected move never touches
the task's status.
"""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.boards.application.authorization_helpers import BoardAuthorization
from app.boards.application.dtos import BoardCardDTO
from app.boards.application.ports import OrgPermissionCheckerPort, ProjectContextPort, TaskStatusRejectedError, TasksContextPort
from app.boards.domain.audit import BoardsAuditEventCategory, BoardsAuditLogRecord
from app.boards.domain.entities import BoardCard, compute_position_between
from app.boards.domain.events import TaskAddedToBoard, TaskMoved, TaskRemovedFromBoard
from app.boards.domain.exceptions import (
    BoardCardNotFoundError,
    BoardNotFoundError,
    ColumnNotFoundError,
    TaskAlreadyOnBoardError,
    TaskNotAccessibleError,
    WipLimitExceededError,
)


def _to_dto(card: BoardCard) -> BoardCardDTO:
    return BoardCardDTO(
        id=card.id, board_id=card.board_id, task_id=card.task_id, column_id=card.column_id,
        swimlane_id=card.swimlane_id, sprint_id=card.sprint_id, position=card.position,
        estimate_type=card.estimate_type.value if card.estimate_type else None, estimate_value=card.estimate_value,
        custom_estimate_label=card.custom_estimate_label,
    )


class CardMovementService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort, tasks_context: TasksContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = BoardAuthorization(permission_checker=permission_checker, project_context=project_context)
        self._tasks_context = tasks_context

    async def add_task_to_board(
        self, *, board_id: EntityId, actor_user_id: UserId, task_id: EntityId, column_id: EntityId | None = None,
    ) -> BoardCardDTO:
        async with self._uow_factory() as uow:
            board = await uow.boards.get_by_id(board_id)
            if board is None:
                raise BoardNotFoundError(board_id)
            await self._authorization.assert_can_move_tasks(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            task = await self._tasks_context.get_task(task_id=task_id)
            if task is None or task.project_id != board.project_id:
                raise TaskNotAccessibleError(task_id)

            if await uow.board_cards.get_by_task(board_id, task_id) is not None:
                raise TaskAlreadyOnBoardError()

            if column_id is not None:
                await self._assert_wip_limit_not_exceeded(uow, column_id)
                existing_cards = await uow.board_cards.list_for_column(column_id)
                position = compute_position_between(existing_cards[-1].position if existing_cards else None, None)
            else:
                backlog_cards = await uow.board_cards.list_backlog_for_board(board_id)
                position = compute_position_between(backlog_cards[-1].position if backlog_cards else None, None)

            card = BoardCard.add_to_board(board_id=board_id, task_id=task_id, column_id=column_id, position=position)
            await uow.board_cards.add(card)
            await uow.audit_logs.add(
                BoardsAuditLogRecord.create(
                    org_id=board.org_id, category=BoardsAuditEventCategory.CARD_CHANGE, action="task_added_to_board",
                    actor_user_id=actor_user_id, resource_type="board", resource_id=str(board_id),
                    metadata={"task_id": str(task_id)},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch(TaskAddedToBoard(aggregate_id=card.id, board_id=board_id, task_id=task_id))
            return _to_dto(card)

    async def remove_task_from_board(self, *, card_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            card = await uow.board_cards.get_by_id(card_id)
            if card is None:
                raise BoardCardNotFoundError(card_id)
            board = await uow.boards.get_by_id(card.board_id)
            await self._authorization.assert_can_move_tasks(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            await uow.board_cards.delete(card_id)
            await uow.commit()
            await self._dispatcher.dispatch(TaskRemovedFromBoard(aggregate_id=card.id, board_id=board.id, task_id=card.task_id))

    async def _assert_wip_limit_not_exceeded(self, uow, column_id: EntityId) -> None:
        column = await uow.board_columns.get_by_id(column_id)
        if column is None:
            raise ColumnNotFoundError(column_id)
        if column.wip_limit is not None:
            current_count = await uow.board_cards.count_for_column(column_id)
            if current_count >= column.wip_limit:
                raise WipLimitExceededError(column.name, column.wip_limit, current_count)

    async def move_task_to_column(
        self, *, card_id: EntityId, actor_user_id: UserId, column_id: EntityId | None,
        previous_card_id: EntityId | None = None, next_card_id: EntityId | None = None,
        swimlane_id: EntityId | None = None,
    ) -> BoardCardDTO:
        async with self._uow_factory() as uow:
            card = await uow.board_cards.get_by_id(card_id)
            if card is None:
                raise BoardCardNotFoundError(card_id)
            board = await uow.boards.get_by_id(card.board_id)
            await self._authorization.assert_can_move_tasks(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            from_column_id = card.column_id
            target_column = None
            if column_id is not None and column_id != from_column_id:
                await self._assert_wip_limit_not_exceeded(uow, column_id)
                target_column = await uow.board_columns.get_by_id(column_id)

            previous_position = None
            if previous_card_id is not None:
                previous_card = await uow.board_cards.get_by_id(previous_card_id)
                previous_position = previous_card.position if previous_card else None
            next_position = None
            if next_card_id is not None:
                next_card = await uow.board_cards.get_by_id(next_card_id)
                next_position = next_card.position if next_card else None

            new_position = compute_position_between(previous_position, next_position)
            card.move_to_column(column_id=column_id, position=new_position, swimlane_id=swimlane_id)
            await uow.board_cards.update(card)
            await uow.commit()

            await self._dispatcher.dispatch(
                TaskMoved(aggregate_id=card.id, board_id=board.id, task_id=card.task_id, from_column_id=from_column_id, to_column_id=column_id)
            )

        # Status sync happens after the board-side transaction commits,
        # via Tasks' own TaskLifecycleService (which enforces that
        # context's configured workflow) — a rejected status transition
        # there does not undo the successful board move; it's surfaced to
        # the caller as a distinct, catchable error.
        if target_column is not None and target_column.mapped_task_status is not None:
            try:
                await self._tasks_context.change_task_status(task_id=card.task_id, actor_user_id=actor_user_id, status=target_column.mapped_task_status)
            except TaskStatusRejectedError:
                raise

        return _to_dto(card)

    async def reorder_task(
        self, *, card_id: EntityId, actor_user_id: UserId, previous_card_id: EntityId | None, next_card_id: EntityId | None,
    ) -> BoardCardDTO:
        """Reorder within the same column/backlog — drag & drop without a
        column change."""
        async with self._uow_factory() as uow:
            card = await uow.board_cards.get_by_id(card_id)
            if card is None:
                raise BoardCardNotFoundError(card_id)
            board = await uow.boards.get_by_id(card.board_id)
            await self._authorization.assert_can_move_tasks(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            previous_position = None
            if previous_card_id is not None:
                previous_card = await uow.board_cards.get_by_id(previous_card_id)
                previous_position = previous_card.position if previous_card else None
            next_position = None
            if next_card_id is not None:
                next_card = await uow.board_cards.get_by_id(next_card_id)
                next_position = next_card.position if next_card else None

            card.move_to_column(column_id=card.column_id, position=compute_position_between(previous_position, next_position))
            await uow.board_cards.update(card)
            await uow.commit()
            return _to_dto(card)

    async def batch_move(
        self, *, actor_user_id: UserId, moves: list[tuple[EntityId, EntityId | None]],
    ) -> list[BoardCardDTO]:
        """Batch Move: move several cards to (possibly different) columns
        in one call — each move still goes through the same WIP-limit and
        authorization checks; a failure partway through does not roll back
        moves already applied in earlier iterations (each move is its own
        transaction, consistent with how the platform's other batch-style
        operations behave when no explicit saga/compensation was
        requested)."""
        results = []
        for card_id, column_id in moves:
            result = await self.move_task_to_column(card_id=card_id, actor_user_id=actor_user_id, column_id=column_id)
            results.append(result)
        return results

    async def list_for_board(self, *, board_id: EntityId) -> list[BoardCardDTO]:
        async with self._uow_factory() as uow:
            cards = await uow.board_cards.list_for_board(board_id)
            return [_to_dto(c) for c in cards]
