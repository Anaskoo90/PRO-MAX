"""ORM row <-> domain entity mapping for the Boards & Agile Management context."""

from __future__ import annotations

from app.boards.domain.audit import BoardsAuditEventCategory, BoardsAuditLogRecord
from app.boards.domain.entities import (
    Board,
    BoardCard,
    BoardColumn,
    BoardStatus,
    BoardType,
    EstimateType,
    Sprint,
    SprintBurndownSnapshot,
    SprintStatus,
    Swimlane,
    SwimlaneStrategy,
)
from app.boards.infrastructure.orm_models import (
    BoardCardOrmModel,
    BoardColumnOrmModel,
    BoardOrmModel,
    BoardsAuditLogOrmModel,
    SprintBurndownSnapshotOrmModel,
    SprintOrmModel,
    SwimlaneOrmModel,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def board_to_domain(row: BoardOrmModel) -> Board:
    return Board(
        id=EntityId(row.id), project_id=EntityId(row.project_id), org_id=OrgId(row.org_id), name=row.name,
        description=row.description, board_type=BoardType(row.board_type),
        swimlane_strategy=SwimlaneStrategy(row.swimlane_strategy), status=BoardStatus(row.status),
        settings=row.settings, archived_at=row.archived_at, deleted_at=row.deleted_at, version=row.version,
    )


def board_to_orm(entity: Board, row: BoardOrmModel | None = None) -> BoardOrmModel:
    row = row or BoardOrmModel(id=entity.id)
    row.project_id = entity.project_id
    row.org_id = entity.org_id
    row.name = entity.name
    row.description = entity.description
    row.board_type = entity.board_type.value
    row.swimlane_strategy = entity.swimlane_strategy.value
    row.status = entity.status.value
    row.settings = entity.settings
    row.archived_at = entity.archived_at
    row.deleted_at = entity.deleted_at
    row.version = entity.version
    return row


def board_column_to_domain(row: BoardColumnOrmModel) -> BoardColumn:
    return BoardColumn(
        id=EntityId(row.id), board_id=EntityId(row.board_id), name=row.name, position=row.position,
        wip_limit=row.wip_limit, color=row.color, mapped_task_status=row.mapped_task_status,
        policies=row.policies, version=row.version,
    )


def board_column_to_orm(entity: BoardColumn, row: BoardColumnOrmModel | None = None) -> BoardColumnOrmModel:
    row = row or BoardColumnOrmModel(id=entity.id, board_id=entity.board_id)
    row.name = entity.name
    row.position = entity.position
    row.wip_limit = entity.wip_limit
    row.color = entity.color
    row.mapped_task_status = entity.mapped_task_status
    row.policies = entity.policies
    row.version = entity.version
    return row


def swimlane_to_domain(row: SwimlaneOrmModel) -> Swimlane:
    return Swimlane(id=EntityId(row.id), board_id=EntityId(row.board_id), name=row.name, position=row.position, version=row.version)


def swimlane_to_orm(entity: Swimlane, row: SwimlaneOrmModel | None = None) -> SwimlaneOrmModel:
    row = row or SwimlaneOrmModel(id=entity.id, board_id=entity.board_id)
    row.name = entity.name
    row.position = entity.position
    row.version = entity.version
    return row


def board_card_to_domain(row: BoardCardOrmModel) -> BoardCard:
    return BoardCard(
        id=EntityId(row.id), board_id=EntityId(row.board_id), task_id=EntityId(row.task_id),
        column_id=EntityId(row.column_id) if row.column_id else None,
        swimlane_id=EntityId(row.swimlane_id) if row.swimlane_id else None,
        sprint_id=EntityId(row.sprint_id) if row.sprint_id else None, position=row.position,
        estimate_type=EstimateType(row.estimate_type) if row.estimate_type else None,
        estimate_value=row.estimate_value, custom_estimate_label=row.custom_estimate_label, added_at=row.added_at,
    )


def board_card_to_orm(entity: BoardCard, row: BoardCardOrmModel | None = None) -> BoardCardOrmModel:
    row = row or BoardCardOrmModel(id=entity.id, board_id=entity.board_id, task_id=entity.task_id, added_at=entity.added_at)
    row.column_id = entity.column_id
    row.swimlane_id = entity.swimlane_id
    row.sprint_id = entity.sprint_id
    row.position = entity.position
    row.estimate_type = entity.estimate_type.value if entity.estimate_type else None
    row.estimate_value = entity.estimate_value
    row.custom_estimate_label = entity.custom_estimate_label
    return row


def sprint_to_domain(row: SprintOrmModel) -> Sprint:
    return Sprint(
        id=EntityId(row.id), board_id=EntityId(row.board_id), name=row.name, goal=row.goal,
        status=SprintStatus(row.status), start_date=row.start_date, end_date=row.end_date, capacity=row.capacity,
        version=row.version,
    )


def sprint_to_orm(entity: Sprint, row: SprintOrmModel | None = None) -> SprintOrmModel:
    row = row or SprintOrmModel(id=entity.id, board_id=entity.board_id)
    row.name = entity.name
    row.goal = entity.goal
    row.status = entity.status.value
    row.start_date = entity.start_date
    row.end_date = entity.end_date
    row.capacity = entity.capacity
    row.version = entity.version
    return row


def burndown_snapshot_to_domain(row: SprintBurndownSnapshotOrmModel) -> SprintBurndownSnapshot:
    return SprintBurndownSnapshot(
        id=EntityId(row.id), sprint_id=EntityId(row.sprint_id), snapshot_date=row.snapshot_date,
        remaining_points=row.remaining_points, remaining_hours=row.remaining_hours, occurred_at=row.occurred_at,
    )


def burndown_snapshot_to_orm(entity: SprintBurndownSnapshot) -> SprintBurndownSnapshotOrmModel:
    return SprintBurndownSnapshotOrmModel(
        id=entity.id, sprint_id=entity.sprint_id, snapshot_date=entity.snapshot_date,
        remaining_points=entity.remaining_points, remaining_hours=entity.remaining_hours,
    )


def audit_log_to_domain(row: BoardsAuditLogOrmModel) -> BoardsAuditLogRecord:
    return BoardsAuditLogRecord(
        id=EntityId(row.id), org_id=OrgId(row.org_id), category=BoardsAuditEventCategory(row.category),
        action=row.action, actor_user_id=UserId(row.actor_user_id) if row.actor_user_id else None,
        resource_type=row.resource_type, resource_id=row.resource_id, metadata=row.metadata_,
        occurred_at=row.occurred_at,
    )


def audit_log_to_orm(entity: BoardsAuditLogRecord) -> BoardsAuditLogOrmModel:
    return BoardsAuditLogOrmModel(
        id=entity.id, org_id=entity.org_id, category=entity.category.value, action=entity.action,
        actor_user_id=entity.actor_user_id, resource_type=entity.resource_type, resource_id=entity.resource_id,
        metadata_=entity.metadata, occurred_at=entity.occurred_at,
    )
