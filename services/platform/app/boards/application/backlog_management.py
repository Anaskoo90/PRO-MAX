"""
Backlog submodule: product backlog, sprint backlog, move between backlog
and board.

Two independent dimensions of "backlog", not conflated:
- Sprint assignment (this module): is a card committed to a sprint (Sprint
  Backlog) or not yet (Product Backlog)?
- Column placement (card_movement.py): is a card visually placed on a
  board column, or sitting unplaced (column_id NULL)?

A card can be in the Product Backlog and already have a column (e.g. a
Kanban board with no sprints at all), or be in a Sprint Backlog and still
unplaced (column_id NULL) until work actually starts on it.
"""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.boards.application.authorization_helpers import BoardAuthorization
from app.boards.application.dtos import BoardCardDTO
from app.boards.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.boards.domain.entities import BoardCard
from app.boards.domain.events import TaskAssignedToSprint, TaskRemovedFromSprint
from app.boards.domain.exceptions import BoardCardNotFoundError, BoardNotFoundError, SprintNotFoundError


def _to_dto(card: BoardCard) -> BoardCardDTO:
    return BoardCardDTO(
        id=card.id, board_id=card.board_id, task_id=card.task_id, column_id=card.column_id,
        swimlane_id=card.swimlane_id, sprint_id=card.sprint_id, position=card.position,
        estimate_type=card.estimate_type.value if card.estimate_type else None, estimate_value=card.estimate_value,
        custom_estimate_label=card.custom_estimate_label,
    )


class BacklogService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = BoardAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def list_product_backlog(self, *, board_id: EntityId) -> list[BoardCardDTO]:
        async with self._uow_factory() as uow:
            cards = await uow.board_cards.list_for_board(board_id)
            return [_to_dto(c) for c in cards if c.sprint_id is None]

    async def list_sprint_backlog(self, *, sprint_id: EntityId) -> list[BoardCardDTO]:
        async with self._uow_factory() as uow:
            cards = await uow.board_cards.list_for_sprint(sprint_id)
            return [_to_dto(c) for c in cards]

    async def move_to_backlog(self, *, card_id: EntityId, actor_user_id: UserId) -> BoardCardDTO:
        """Move Between Backlog and Board: pulls a card off its column,
        back into the unplaced backlog view — sprint assignment (if any)
        is untouched, since column placement and sprint membership are
        independent dimensions."""
        async with self._uow_factory() as uow:
            card = await uow.board_cards.get_by_id(card_id)
            if card is None:
                raise BoardCardNotFoundError(card_id)
            board = await uow.boards.get_by_id(card.board_id)
            await self._authorization.assert_can_move_tasks(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            card.move_to_column(column_id=None, position=0.0)
            await uow.board_cards.update(card)
            await uow.commit()
            return _to_dto(card)

    async def assign_to_sprint(self, *, card_id: EntityId, actor_user_id: UserId, sprint_id: EntityId) -> BoardCardDTO:
        async with self._uow_factory() as uow:
            card = await uow.board_cards.get_by_id(card_id)
            if card is None:
                raise BoardCardNotFoundError(card_id)
            board = await uow.boards.get_by_id(card.board_id)
            await self._authorization.assert_can_manage_sprint(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            sprint = await uow.sprints.get_by_id(sprint_id)
            if sprint is None or sprint.board_id != card.board_id:
                raise SprintNotFoundError(sprint_id)

            card.assign_to_sprint(sprint_id)
            await uow.board_cards.update(card)
            await uow.commit()
            await self._dispatcher.dispatch(TaskAssignedToSprint(aggregate_id=card.id, sprint_id=sprint_id, task_id=card.task_id))
            return _to_dto(card)

    async def remove_from_sprint(self, *, card_id: EntityId, actor_user_id: UserId) -> BoardCardDTO:
        async with self._uow_factory() as uow:
            card = await uow.board_cards.get_by_id(card_id)
            if card is None:
                raise BoardCardNotFoundError(card_id)
            board = await uow.boards.get_by_id(card.board_id)
            await self._authorization.assert_can_manage_sprint(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            sprint_id = card.sprint_id
            card.remove_from_sprint()
            await uow.board_cards.update(card)
            await uow.commit()
            if sprint_id is not None:
                await self._dispatcher.dispatch(TaskRemovedFromSprint(aggregate_id=card.id, sprint_id=sprint_id, task_id=card.task_id))
            return _to_dto(card)
