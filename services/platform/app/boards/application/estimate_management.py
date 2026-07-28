"""Estimates submodule: story points, hours, custom estimates — set on a
BoardCard (not on Task, which the frozen Tasks & Work Management context
was never scoped to hold estimation data for)."""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.boards.application.authorization_helpers import BoardAuthorization
from app.boards.application.dtos import BoardCardDTO
from app.boards.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.boards.domain.entities import BoardCard, EstimateType
from app.boards.domain.events import TaskEstimateSet
from app.boards.domain.exceptions import BoardCardNotFoundError, BoardNotFoundError


def _to_dto(card: BoardCard) -> BoardCardDTO:
    return BoardCardDTO(
        id=card.id, board_id=card.board_id, task_id=card.task_id, column_id=card.column_id,
        swimlane_id=card.swimlane_id, sprint_id=card.sprint_id, position=card.position,
        estimate_type=card.estimate_type.value if card.estimate_type else None, estimate_value=card.estimate_value,
        custom_estimate_label=card.custom_estimate_label,
    )


class EstimateService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = BoardAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def set_estimate(
        self, *, card_id: EntityId, actor_user_id: UserId, estimate_type: EstimateType, value: float,
        custom_label: str | None = None,
    ) -> BoardCardDTO:
        async with self._uow_factory() as uow:
            card = await uow.board_cards.get_by_id(card_id)
            if card is None:
                raise BoardCardNotFoundError(card_id)
            board = await uow.boards.get_by_id(card.board_id)
            if board is None:
                raise BoardNotFoundError(card.board_id)
            await self._authorization.assert_can_move_tasks(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            card.set_estimate(estimate_type=estimate_type, value=value, custom_label=custom_label)
            await uow.board_cards.update(card)
            await uow.commit()
            await self._dispatcher.dispatch(TaskEstimateSet(aggregate_id=card.id, estimate_type=estimate_type.value))
            return _to_dto(card)
