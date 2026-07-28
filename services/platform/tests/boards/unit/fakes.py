"""In-memory fakes satisfying the Boards & Agile Management repository
Protocols and application ports — mirrors tests/tasks/unit/fakes.py exactly."""

from __future__ import annotations

from datetime import date

from app.boards.application.ports import ProjectMemberSummary, ProjectSummary, TaskSummary, TaskStatusRejectedError
from app.boards.domain.entities import Board, BoardCard, BoardColumn, Sprint, SprintBurndownSnapshot, Swimlane
from app.platform_core.shared_kernel.types import EntityId


class FakeBoardRepository:
    def __init__(self) -> None:
        self.boards: dict[EntityId, Board] = {}

    async def get_by_id(self, board_id: EntityId) -> Board | None:
        board = self.boards.get(board_id)
        return board if board and board.deleted_at is None else None

    async def list_for_project(self, project_id: EntityId, *, include_archived: bool = False) -> list[Board]:
        return [
            b for b in self.boards.values()
            if b.project_id == project_id and b.deleted_at is None and (include_archived or b.status.value != "archived")
        ]

    async def add(self, board: Board) -> None:
        self.boards[board.id] = board

    async def update(self, board: Board) -> None:
        self.boards[board.id] = board


class FakeBoardColumnRepository:
    def __init__(self) -> None:
        self.columns: dict[EntityId, BoardColumn] = {}

    async def get_by_id(self, column_id: EntityId) -> BoardColumn | None:
        return self.columns.get(column_id)

    async def get_by_name(self, board_id: EntityId, name: str) -> BoardColumn | None:
        return next((c for c in self.columns.values() if c.board_id == board_id and c.name == name), None)

    async def list_for_board(self, board_id: EntityId) -> list[BoardColumn]:
        return sorted((c for c in self.columns.values() if c.board_id == board_id), key=lambda c: c.position)

    async def add(self, column: BoardColumn) -> None:
        self.columns[column.id] = column

    async def update(self, column: BoardColumn) -> None:
        self.columns[column.id] = column

    async def delete(self, column_id: EntityId) -> None:
        self.columns.pop(column_id, None)


class FakeSwimlaneRepository:
    def __init__(self) -> None:
        self.swimlanes: dict[EntityId, Swimlane] = {}

    async def get_by_id(self, swimlane_id: EntityId) -> Swimlane | None:
        return self.swimlanes.get(swimlane_id)

    async def list_for_board(self, board_id: EntityId) -> list[Swimlane]:
        return sorted((s for s in self.swimlanes.values() if s.board_id == board_id), key=lambda s: s.position)

    async def add(self, swimlane: Swimlane) -> None:
        self.swimlanes[swimlane.id] = swimlane

    async def update(self, swimlane: Swimlane) -> None:
        self.swimlanes[swimlane.id] = swimlane

    async def delete(self, swimlane_id: EntityId) -> None:
        self.swimlanes.pop(swimlane_id, None)


class FakeBoardCardRepository:
    def __init__(self) -> None:
        self.cards: dict[EntityId, BoardCard] = {}

    async def get_by_id(self, card_id: EntityId) -> BoardCard | None:
        return self.cards.get(card_id)

    async def get_by_task(self, board_id: EntityId, task_id: EntityId) -> BoardCard | None:
        return next((c for c in self.cards.values() if c.board_id == board_id and c.task_id == task_id), None)

    async def list_for_board(self, board_id: EntityId) -> list[BoardCard]:
        return [c for c in self.cards.values() if c.board_id == board_id]

    async def list_for_column(self, column_id: EntityId) -> list[BoardCard]:
        return sorted((c for c in self.cards.values() if c.column_id == column_id), key=lambda c: c.position)

    async def list_for_sprint(self, sprint_id: EntityId) -> list[BoardCard]:
        return [c for c in self.cards.values() if c.sprint_id == sprint_id]

    async def list_backlog_for_board(self, board_id: EntityId) -> list[BoardCard]:
        return sorted(
            (c for c in self.cards.values() if c.board_id == board_id and c.column_id is None), key=lambda c: c.position
        )

    async def count_for_column(self, column_id: EntityId) -> int:
        return sum(1 for c in self.cards.values() if c.column_id == column_id)

    async def add(self, card: BoardCard) -> None:
        self.cards[card.id] = card

    async def update(self, card: BoardCard) -> None:
        self.cards[card.id] = card

    async def delete(self, card_id: EntityId) -> None:
        self.cards.pop(card_id, None)


class FakeSprintRepository:
    def __init__(self) -> None:
        self.sprints: dict[EntityId, Sprint] = {}

    async def get_by_id(self, sprint_id: EntityId) -> Sprint | None:
        return self.sprints.get(sprint_id)

    async def list_for_board(self, board_id: EntityId) -> list[Sprint]:
        return [s for s in self.sprints.values() if s.board_id == board_id]

    async def get_active_for_board(self, board_id: EntityId) -> Sprint | None:
        return next((s for s in self.sprints.values() if s.board_id == board_id and s.is_active()), None)

    async def list_all_active(self) -> list[Sprint]:
        return [s for s in self.sprints.values() if s.is_active()]

    async def add(self, sprint: Sprint) -> None:
        self.sprints[sprint.id] = sprint

    async def update(self, sprint: Sprint) -> None:
        self.sprints[sprint.id] = sprint


class FakeSprintBurndownSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: list[SprintBurndownSnapshot] = []

    async def add(self, snapshot: SprintBurndownSnapshot) -> None:
        self.snapshots.append(snapshot)

    async def get_for_day(self, sprint_id: EntityId, snapshot_date: date) -> SprintBurndownSnapshot | None:
        return next((s for s in self.snapshots if s.sprint_id == sprint_id and s.snapshot_date == snapshot_date), None)

    async def list_for_sprint(self, sprint_id: EntityId) -> list[SprintBurndownSnapshot]:
        return [s for s in self.snapshots if s.sprint_id == sprint_id]


class FakeBoardsAuditLogRepository:
    def __init__(self) -> None:
        self.records: list = []

    async def add(self, record) -> None:
        self.records.append(record)

    async def list_for_org(self, org_id, *, category=None, limit: int = 50):
        results = [r for r in self.records if r.org_id == org_id]
        if category is not None:
            results = [r for r in results if r.category == category]
        return results[:limit]


class FakeOutboxWriter:
    async def append(self, event) -> None:
        pass


class FakeBoardsUnitOfWork:
    def __init__(self) -> None:
        self.boards = FakeBoardRepository()
        self.board_columns = FakeBoardColumnRepository()
        self.swimlanes = FakeSwimlaneRepository()
        self.board_cards = FakeBoardCardRepository()
        self.sprints = FakeSprintRepository()
        self.sprint_burndown_snapshots = FakeSprintBurndownSnapshotRepository()
        self.audit_logs = FakeBoardsAuditLogRepository()
        self.outbox = FakeOutboxWriter()

    async def __aenter__(self) -> "FakeBoardsUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class AllowAllPermissionChecker:
    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return True


class DenyAllPermissionChecker:
    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return False


class FakeProjectContext:
    """Fakes ProjectContextPort — the ACL boundary to Projects & Workspaces."""

    def __init__(self, *, project: ProjectSummary, members: list[ProjectMemberSummary] | None = None) -> None:
        self.project = project
        self.members = members or []

    async def get_project(self, *, project_id) -> ProjectSummary | None:
        return self.project if self.project.id == project_id else None

    async def get_member(self, *, project_id, user_id) -> ProjectMemberSummary | None:
        if project_id != self.project.id:
            return None
        return next((m for m in self.members if m.user_id == user_id), None)

    async def list_members(self, *, project_id) -> list[ProjectMemberSummary]:
        return list(self.members) if project_id == self.project.id else []


class FakeTasksContext:
    """Fakes TasksContextPort — the ACL boundary to Tasks & Work Management."""

    def __init__(self, *, tasks: list[TaskSummary] | None = None, reject_statuses: set[str] | None = None) -> None:
        self.tasks_by_id = {t.id: t for t in (tasks or [])}
        self._reject_statuses = reject_statuses or set()
        self.assignee_ids: dict[EntityId, list] = {}
        self.label_ids: dict[EntityId, list] = {}
        self.status_changes: list[tuple] = []

    async def get_task(self, *, task_id) -> TaskSummary | None:
        return self.tasks_by_id.get(task_id)

    async def list_tasks_for_project(self, *, project_id, include_archived: bool = False) -> list[TaskSummary]:
        return [t for t in self.tasks_by_id.values() if t.project_id == project_id]

    async def change_task_status(self, *, task_id, actor_user_id, status: str) -> None:
        if status in self._reject_statuses:
            raise TaskStatusRejectedError(f"'{status}' rejected by Tasks")
        self.status_changes.append((task_id, status))
        existing = self.tasks_by_id.get(task_id)
        if existing is not None:
            self.tasks_by_id[task_id] = TaskSummary(
                id=existing.id, project_id=existing.project_id, org_id=existing.org_id, title=existing.title,
                status=status, priority=existing.priority,
            )

    async def list_assignee_ids(self, *, task_id) -> list:
        return self.assignee_ids.get(task_id, [])

    async def list_label_ids(self, *, task_id) -> list:
        return self.label_ids.get(task_id, [])
