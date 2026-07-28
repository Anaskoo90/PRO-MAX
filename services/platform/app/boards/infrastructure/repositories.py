"""SQLAlchemy-backed implementations of the Boards & Agile Management repository Protocols."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.boards.domain.audit import BoardsAuditEventCategory, BoardsAuditLogRecord
from app.boards.domain.entities import Board, BoardCard, BoardColumn, Sprint, SprintBurndownSnapshot, Swimlane
from app.boards.infrastructure import mappers
from app.boards.infrastructure.orm_models import (
    BoardCardOrmModel,
    BoardColumnOrmModel,
    BoardOrmModel,
    BoardsAuditLogOrmModel,
    SprintBurndownSnapshotOrmModel,
    SprintOrmModel,
    SwimlaneOrmModel,
)
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId


class SqlAlchemyBoardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, board_id: EntityId) -> Board | None:
        row = await self._session.get(BoardOrmModel, board_id)
        return mappers.board_to_domain(row) if row and row.deleted_at is None else None

    async def list_for_project(self, project_id: EntityId, *, include_archived: bool = False) -> list[Board]:
        stmt = select(BoardOrmModel).where(BoardOrmModel.project_id == project_id, BoardOrmModel.deleted_at.is_(None))
        if not include_archived:
            stmt = stmt.where(BoardOrmModel.status != "archived")
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.board_to_domain(r) for r in rows]

    async def add(self, board: Board) -> None:
        self._session.add(mappers.board_to_orm(board))

    async def update(self, board: Board) -> None:
        row = await self._session.get(BoardOrmModel, board.id)
        if row is None:
            raise ValueError(f"Board {board.id} not found for update")
        if row.version != board.version:
            raise ConcurrencyConflictError("Board", board.id)
        mappers.board_to_orm(board, row)
        row.version = board.version + 1
        board.version += 1


class SqlAlchemyBoardColumnRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, column_id: EntityId) -> BoardColumn | None:
        row = await self._session.get(BoardColumnOrmModel, column_id)
        return mappers.board_column_to_domain(row) if row else None

    async def get_by_name(self, board_id: EntityId, name: str) -> BoardColumn | None:
        stmt = select(BoardColumnOrmModel).where(BoardColumnOrmModel.board_id == board_id, BoardColumnOrmModel.name == name)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.board_column_to_domain(row) if row else None

    async def list_for_board(self, board_id: EntityId) -> list[BoardColumn]:
        stmt = select(BoardColumnOrmModel).where(BoardColumnOrmModel.board_id == board_id).order_by(BoardColumnOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.board_column_to_domain(r) for r in rows]

    async def add(self, column: BoardColumn) -> None:
        self._session.add(mappers.board_column_to_orm(column))

    async def update(self, column: BoardColumn) -> None:
        row = await self._session.get(BoardColumnOrmModel, column.id)
        if row is None:
            raise ValueError(f"BoardColumn {column.id} not found for update")
        if row.version != column.version:
            raise ConcurrencyConflictError("BoardColumn", column.id)
        mappers.board_column_to_orm(column, row)
        row.version = column.version + 1
        column.version += 1

    async def delete(self, column_id: EntityId) -> None:
        row = await self._session.get(BoardColumnOrmModel, column_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemySwimlaneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, swimlane_id: EntityId) -> Swimlane | None:
        row = await self._session.get(SwimlaneOrmModel, swimlane_id)
        return mappers.swimlane_to_domain(row) if row else None

    async def list_for_board(self, board_id: EntityId) -> list[Swimlane]:
        stmt = select(SwimlaneOrmModel).where(SwimlaneOrmModel.board_id == board_id).order_by(SwimlaneOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.swimlane_to_domain(r) for r in rows]

    async def add(self, swimlane: Swimlane) -> None:
        self._session.add(mappers.swimlane_to_orm(swimlane))

    async def update(self, swimlane: Swimlane) -> None:
        row = await self._session.get(SwimlaneOrmModel, swimlane.id)
        if row is None:
            raise ValueError(f"Swimlane {swimlane.id} not found for update")
        mappers.swimlane_to_orm(swimlane, row)

    async def delete(self, swimlane_id: EntityId) -> None:
        row = await self._session.get(SwimlaneOrmModel, swimlane_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyBoardCardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, card_id: EntityId) -> BoardCard | None:
        row = await self._session.get(BoardCardOrmModel, card_id)
        return mappers.board_card_to_domain(row) if row else None

    async def get_by_task(self, board_id: EntityId, task_id: EntityId) -> BoardCard | None:
        stmt = select(BoardCardOrmModel).where(BoardCardOrmModel.board_id == board_id, BoardCardOrmModel.task_id == task_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.board_card_to_domain(row) if row else None

    async def list_for_board(self, board_id: EntityId) -> list[BoardCard]:
        stmt = select(BoardCardOrmModel).where(BoardCardOrmModel.board_id == board_id).order_by(BoardCardOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.board_card_to_domain(r) for r in rows]

    async def list_for_column(self, column_id: EntityId) -> list[BoardCard]:
        stmt = select(BoardCardOrmModel).where(BoardCardOrmModel.column_id == column_id).order_by(BoardCardOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.board_card_to_domain(r) for r in rows]

    async def list_for_sprint(self, sprint_id: EntityId) -> list[BoardCard]:
        stmt = select(BoardCardOrmModel).where(BoardCardOrmModel.sprint_id == sprint_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.board_card_to_domain(r) for r in rows]

    async def list_backlog_for_board(self, board_id: EntityId) -> list[BoardCard]:
        stmt = select(BoardCardOrmModel).where(BoardCardOrmModel.board_id == board_id, BoardCardOrmModel.column_id.is_(None))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.board_card_to_domain(r) for r in rows]

    async def count_for_column(self, column_id: EntityId) -> int:
        stmt = select(func.count()).select_from(BoardCardOrmModel).where(BoardCardOrmModel.column_id == column_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def add(self, card: BoardCard) -> None:
        self._session.add(mappers.board_card_to_orm(card))

    async def update(self, card: BoardCard) -> None:
        row = await self._session.get(BoardCardOrmModel, card.id)
        if row is None:
            raise ValueError(f"BoardCard {card.id} not found for update")
        mappers.board_card_to_orm(card, row)

    async def delete(self, card_id: EntityId) -> None:
        row = await self._session.get(BoardCardOrmModel, card_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemySprintRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, sprint_id: EntityId) -> Sprint | None:
        row = await self._session.get(SprintOrmModel, sprint_id)
        return mappers.sprint_to_domain(row) if row else None

    async def list_for_board(self, board_id: EntityId) -> list[Sprint]:
        stmt = select(SprintOrmModel).where(SprintOrmModel.board_id == board_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.sprint_to_domain(r) for r in rows]

    async def get_active_for_board(self, board_id: EntityId) -> Sprint | None:
        stmt = select(SprintOrmModel).where(SprintOrmModel.board_id == board_id, SprintOrmModel.status == "active")
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.sprint_to_domain(row) if row else None

    async def list_all_active(self) -> list[Sprint]:
        stmt = select(SprintOrmModel).where(SprintOrmModel.status == "active")
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.sprint_to_domain(r) for r in rows]

    async def add(self, sprint: Sprint) -> None:
        self._session.add(mappers.sprint_to_orm(sprint))

    async def update(self, sprint: Sprint) -> None:
        row = await self._session.get(SprintOrmModel, sprint.id)
        if row is None:
            raise ValueError(f"Sprint {sprint.id} not found for update")
        if row.version != sprint.version:
            raise ConcurrencyConflictError("Sprint", sprint.id)
        mappers.sprint_to_orm(sprint, row)
        row.version = sprint.version + 1
        sprint.version += 1


class SqlAlchemySprintBurndownSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: SprintBurndownSnapshot) -> None:
        self._session.add(mappers.burndown_snapshot_to_orm(snapshot))

    async def get_for_day(self, sprint_id: EntityId, snapshot_date: date) -> SprintBurndownSnapshot | None:
        stmt = select(SprintBurndownSnapshotOrmModel).where(
            SprintBurndownSnapshotOrmModel.sprint_id == sprint_id,
            SprintBurndownSnapshotOrmModel.snapshot_date == snapshot_date,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.burndown_snapshot_to_domain(row) if row else None

    async def list_for_sprint(self, sprint_id: EntityId) -> list[SprintBurndownSnapshot]:
        stmt = (
            select(SprintBurndownSnapshotOrmModel)
            .where(SprintBurndownSnapshotOrmModel.sprint_id == sprint_id)
            .order_by(SprintBurndownSnapshotOrmModel.snapshot_date)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.burndown_snapshot_to_domain(r) for r in rows]


class SqlAlchemyBoardsAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: BoardsAuditLogRecord) -> None:
        self._session.add(mappers.audit_log_to_orm(record))

    async def list_for_org(
        self, org_id: OrgId, *, category: BoardsAuditEventCategory | None = None, limit: int = 50
    ) -> list[BoardsAuditLogRecord]:
        stmt = select(BoardsAuditLogOrmModel).where(BoardsAuditLogOrmModel.org_id == org_id)
        if category is not None:
            stmt = stmt.where(BoardsAuditLogOrmModel.category == category.value)
        stmt = stmt.order_by(BoardsAuditLogOrmModel.occurred_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.audit_log_to_domain(r) for r in rows]
