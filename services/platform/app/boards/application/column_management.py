"""Columns submodule: create, rename, delete, reorder; WIP limits, colors,
policies."""

from __future__ import annotations

import re
from typing import Any

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.boards.application.authorization_helpers import BoardAuthorization
from app.boards.application.dtos import BoardColumnDTO
from app.boards.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.boards.domain.audit import BoardsAuditEventCategory, BoardsAuditLogRecord
from app.boards.domain.entities import BoardColumn, compute_position_between
from app.boards.domain.events import ColumnCreated, ColumnDeleted, ColumnReordered, ColumnUpdated
from app.boards.domain.exceptions import (
    BoardNotFoundError,
    ColumnNameAlreadyExistsError,
    ColumnNotFoundError,
    InvalidColumnColorError,
)

_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_color(color: str) -> str:
    if not _HEX_COLOR_PATTERN.match(color):
        raise InvalidColumnColorError(color)
    return color


def _to_dto(column: BoardColumn, *, card_count: int = 0) -> BoardColumnDTO:
    return BoardColumnDTO(
        id=column.id, board_id=column.board_id, name=column.name, position=column.position, wip_limit=column.wip_limit,
        color=column.color, mapped_task_status=column.mapped_task_status, policies=column.policies, card_count=card_count,
    )


class ColumnService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = BoardAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def create_column(
        self, *, board_id: EntityId, actor_user_id: UserId, name: str, wip_limit: int | None = None,
        color: str = "#94A3B8", mapped_task_status: str | None = None,
    ) -> BoardColumnDTO:
        _validate_color(color)
        async with self._uow_factory() as uow:
            board = await uow.boards.get_by_id(board_id)
            if board is None:
                raise BoardNotFoundError(board_id)
            await self._authorization.assert_can_manage(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)

            if await uow.board_columns.get_by_name(board_id, name) is not None:
                raise ColumnNameAlreadyExistsError(name)

            existing = await uow.board_columns.list_for_board(board_id)
            position = compute_position_between(existing[-1].position if existing else None, None)
            column = BoardColumn.create(board_id=board_id, name=name, position=position, wip_limit=wip_limit, color=color, mapped_task_status=mapped_task_status)
            await uow.board_columns.add(column)
            await uow.audit_logs.add(
                BoardsAuditLogRecord.create(
                    org_id=board.org_id, category=BoardsAuditEventCategory.COLUMN_CHANGE, action="column_created",
                    actor_user_id=actor_user_id, resource_type="column", resource_id=str(column.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch(ColumnCreated(aggregate_id=column.id, board_id=board_id, name=name))
            return _to_dto(column)

    async def list_for_board(self, *, board_id: EntityId) -> list[BoardColumnDTO]:
        async with self._uow_factory() as uow:
            columns = await uow.board_columns.list_for_board(board_id)
            result = []
            for column in columns:
                count = await uow.board_cards.count_for_column(column.id)
                result.append(_to_dto(column, card_count=count))
            return result

    async def _load_column_and_authorize(self, uow, *, column_id: EntityId, actor_user_id: UserId) -> BoardColumn:
        column = await uow.board_columns.get_by_id(column_id)
        if column is None:
            raise ColumnNotFoundError(column_id)
        board = await uow.boards.get_by_id(column.board_id)
        if board is None:
            raise BoardNotFoundError(column.board_id)
        await self._authorization.assert_can_manage(project_id=board.project_id, org_id=board.org_id, user_id=actor_user_id)
        return column

    async def rename_column(self, *, column_id: EntityId, actor_user_id: UserId, name: str) -> BoardColumnDTO:
        async with self._uow_factory() as uow:
            column = await self._load_column_and_authorize(uow, column_id=column_id, actor_user_id=actor_user_id)
            if await uow.board_columns.get_by_name(column.board_id, name) is not None:
                raise ColumnNameAlreadyExistsError(name)
            column.rename(name)
            await uow.board_columns.update(column)
            await uow.commit()
            await self._dispatcher.dispatch(ColumnUpdated(aggregate_id=column.id))
            return _to_dto(column)

    async def set_wip_limit(self, *, column_id: EntityId, actor_user_id: UserId, wip_limit: int | None) -> BoardColumnDTO:
        async with self._uow_factory() as uow:
            column = await self._load_column_and_authorize(uow, column_id=column_id, actor_user_id=actor_user_id)
            column.set_wip_limit(wip_limit)
            await uow.board_columns.update(column)
            await uow.commit()
            await self._dispatcher.dispatch(ColumnUpdated(aggregate_id=column.id))
            return _to_dto(column)

    async def set_color(self, *, column_id: EntityId, actor_user_id: UserId, color: str) -> BoardColumnDTO:
        _validate_color(color)
        async with self._uow_factory() as uow:
            column = await self._load_column_and_authorize(uow, column_id=column_id, actor_user_id=actor_user_id)
            column.set_color(color)
            await uow.board_columns.update(column)
            await uow.commit()
            await self._dispatcher.dispatch(ColumnUpdated(aggregate_id=column.id))
            return _to_dto(column)

    async def set_policies(self, *, column_id: EntityId, actor_user_id: UserId, policies: dict[str, Any]) -> BoardColumnDTO:
        async with self._uow_factory() as uow:
            column = await self._load_column_and_authorize(uow, column_id=column_id, actor_user_id=actor_user_id)
            column.set_policies(policies)
            await uow.board_columns.update(column)
            await uow.commit()
            await self._dispatcher.dispatch(ColumnUpdated(aggregate_id=column.id))
            return _to_dto(column)

    async def set_mapped_task_status(self, *, column_id: EntityId, actor_user_id: UserId, status: str | None) -> BoardColumnDTO:
        async with self._uow_factory() as uow:
            column = await self._load_column_and_authorize(uow, column_id=column_id, actor_user_id=actor_user_id)
            column.set_mapped_task_status(status)
            await uow.board_columns.update(column)
            await uow.commit()
            await self._dispatcher.dispatch(ColumnUpdated(aggregate_id=column.id))
            return _to_dto(column)

    async def reorder_column(
        self, *, column_id: EntityId, actor_user_id: UserId, previous_column_id: EntityId | None,
        next_column_id: EntityId | None,
    ) -> BoardColumnDTO:
        async with self._uow_factory() as uow:
            column = await self._load_column_and_authorize(uow, column_id=column_id, actor_user_id=actor_user_id)

            previous_position = None
            if previous_column_id is not None:
                previous_column = await uow.board_columns.get_by_id(previous_column_id)
                previous_position = previous_column.position if previous_column else None
            next_position = None
            if next_column_id is not None:
                next_column = await uow.board_columns.get_by_id(next_column_id)
                next_position = next_column.position if next_column else None

            column.set_position(compute_position_between(previous_position, next_position))
            await uow.board_columns.update(column)
            await uow.commit()
            await self._dispatcher.dispatch(ColumnReordered(aggregate_id=column.id, position=column.position))
            return _to_dto(column)

    async def delete_column(self, *, column_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            column = await self._load_column_and_authorize(uow, column_id=column_id, actor_user_id=actor_user_id)
            board = await uow.boards.get_by_id(column.board_id)

            cards = await uow.board_cards.list_for_column(column_id)
            for card in cards:
                card.move_to_column(column_id=None, position=0.0)
                await uow.board_cards.update(card)

            await uow.board_columns.delete(column_id)
            await uow.audit_logs.add(
                BoardsAuditLogRecord.create(
                    org_id=board.org_id, category=BoardsAuditEventCategory.COLUMN_CHANGE, action="column_deleted",
                    actor_user_id=actor_user_id, resource_type="column", resource_id=str(column_id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch(ColumnDeleted(aggregate_id=column_id))
