"""Board Aggregate submodule: create, update, archive, restore, delete."""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.boards.application.authorization_helpers import BoardAuthorization
from app.boards.application.dtos import BoardDTO
from app.boards.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.boards.domain.audit import BoardsAuditEventCategory, BoardsAuditLogRecord
from app.boards.domain.entities import Board, BoardStatus, BoardType, SwimlaneStrategy
from app.boards.domain.exceptions import BoardNotFoundError, InsufficientBoardPermissionError


def _to_dto(board: Board) -> BoardDTO:
    return BoardDTO(
        id=board.id, project_id=board.project_id, org_id=board.org_id, name=board.name, description=board.description,
        board_type=board.board_type.value, swimlane_strategy=board.swimlane_strategy.value, status=board.status.value,
        settings=board.settings, archived_at=board.archived_at,
    )


class BoardService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = BoardAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def create_board(
        self, *, project_id: EntityId, org_id: OrgId, actor_user_id: UserId, name: str, description: str = "",
        board_type: BoardType = BoardType.KANBAN, swimlane_strategy: SwimlaneStrategy = SwimlaneStrategy.NONE,
    ) -> BoardDTO:
        await self._authorization.assert_project_accessible(project_id=project_id, org_id=org_id)
        if not await self._authorization.can_manage(project_id=project_id, org_id=org_id, user_id=actor_user_id):
            raise InsufficientBoardPermissionError(("owner", "admin", "contributor"))

        async with self._uow_factory() as uow:
            board = Board.create(
                project_id=project_id, org_id=org_id, name=name, description=description, board_type=board_type,
                swimlane_strategy=swimlane_strategy,
            )
            await uow.boards.add(board)
            events = board.pull_domain_events()
            await uow.audit_logs.add(
                BoardsAuditLogRecord.create(
                    org_id=org_id, category=BoardsAuditEventCategory.BOARD_CHANGE, action="board_created",
                    actor_user_id=actor_user_id, resource_type="board", resource_id=str(board.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(board)

    async def get(self, *, board_id: EntityId) -> BoardDTO:
        async with self._uow_factory() as uow:
            board = await uow.boards.get_by_id(board_id)
            if board is None:
                raise BoardNotFoundError(board_id)
            return _to_dto(board)

    async def list_for_project(self, *, project_id: EntityId, include_archived: bool = False) -> list[BoardDTO]:
        async with self._uow_factory() as uow:
            boards = await uow.boards.list_for_project(project_id, include_archived=include_archived)
            return [_to_dto(b) for b in boards]

    async def _load_and_authorize(self, uow, *, board_id: EntityId, actor_user_id: UserId) -> Board:
        board = await uow.boards.get_by_id(board_id)
        if board is None:
            raise BoardNotFoundError(board_id)
        board.assert_not_deleted()
        await self._authorization.assert_can_manage(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)
        return board

    async def update(
        self, *, board_id: EntityId, actor_user_id: UserId, name: str | None = None, description: str | None = None,
    ) -> BoardDTO:
        async with self._uow_factory() as uow:
            board = await self._load_and_authorize(uow, board_id=board_id, actor_user_id=actor_user_id)
            board.update(name=name, description=description)
            await uow.boards.update(board)
            events = board.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(board)

    async def update_settings(self, *, board_id: EntityId, actor_user_id: UserId, patch: dict) -> BoardDTO:
        async with self._uow_factory() as uow:
            board = await self._load_and_authorize(uow, board_id=board_id, actor_user_id=actor_user_id)
            board.update_settings(patch)
            await uow.boards.update(board)
            events = board.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(board)

    async def change_swimlane_strategy(self, *, board_id: EntityId, actor_user_id: UserId, strategy: SwimlaneStrategy) -> BoardDTO:
        async with self._uow_factory() as uow:
            board = await self._load_and_authorize(uow, board_id=board_id, actor_user_id=actor_user_id)
            board.change_swimlane_strategy(strategy)
            await uow.boards.update(board)
            events = board.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(board)

    async def archive(self, *, board_id: EntityId, actor_user_id: UserId) -> BoardDTO:
        async with self._uow_factory() as uow:
            board = await self._load_and_authorize(uow, board_id=board_id, actor_user_id=actor_user_id)
            board.archive()
            await uow.boards.update(board)
            events = board.pull_domain_events()
            await uow.audit_logs.add(
                BoardsAuditLogRecord.create(
                    org_id=board.org_id, category=BoardsAuditEventCategory.BOARD_CHANGE, action="board_archived",
                    actor_user_id=actor_user_id, resource_type="board", resource_id=str(board.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(board)

    async def restore(self, *, board_id: EntityId, actor_user_id: UserId) -> BoardDTO:
        async with self._uow_factory() as uow:
            board = await self._load_and_authorize(uow, board_id=board_id, actor_user_id=actor_user_id)
            board.restore()
            await uow.boards.update(board)
            events = board.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(board)

    async def delete(self, *, board_id: EntityId, actor_user_id: UserId) -> None:
        """Soft delete (deleted_at) — distinct from archive, per the
        platform-wide convention that entity tables never hard-delete."""
        async with self._uow_factory() as uow:
            board = await self._load_and_authorize(uow, board_id=board_id, actor_user_id=actor_user_id)
            board.mark_deleted()
            await uow.boards.update(board)
            events = board.pull_domain_events()
            await uow.audit_logs.add(
                BoardsAuditLogRecord.create(
                    org_id=board.org_id, category=BoardsAuditEventCategory.BOARD_CHANGE, action="board_deleted",
                    actor_user_id=actor_user_id, resource_type="board", resource_id=str(board.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
