"""In-memory fakes satisfying the Tasks & Work Management repository
Protocols and application ports — mirrors tests/identity/unit/fakes.py and
tests/projects/unit/fakes.py exactly."""

from __future__ import annotations

from app.tasks.application.ports import ProjectMemberSummary, ProjectSummary, UserSummary
from app.tasks.domain.entities import (
    Label,
    Task,
    TaskAssignment,
    TaskAssignmentHistoryRecord,
    TaskDependency,
    TaskLabel,
    TaskRelation,
)
from app.tasks.domain.workflow import TERMINAL_STATUSES, WorkflowDefinition
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.platform_core.shared_kernel.utils import utcnow


class FakeTaskRepository:
    def __init__(self) -> None:
        self.tasks: dict[EntityId, Task] = {}

    async def get_by_id(self, task_id: EntityId) -> Task | None:
        task = self.tasks.get(task_id)
        return task if task and task.deleted_at is None else None

    async def list_for_project(self, project_id: EntityId, *, include_archived: bool = False) -> list[Task]:
        return [
            t for t in self.tasks.values()
            if t.project_id == project_id and t.deleted_at is None and (include_archived or not t.is_archived)
        ]

    async def list_subtasks(self, parent_task_id: EntityId) -> list[Task]:
        return [t for t in self.tasks.values() if t.parent_task_id == parent_task_id and t.deleted_at is None]

    async def list_by_ids(self, task_ids: list[EntityId]) -> list[Task]:
        return [self.tasks[t] for t in task_ids if t in self.tasks and self.tasks[t].deleted_at is None]

    async def list_overdue_for_project(self, project_id: EntityId) -> list[Task]:
        now = utcnow()
        return [
            t for t in self.tasks.values()
            if t.project_id == project_id and t.deleted_at is None and t.due_date is not None
            and t.due_date < now and t.status not in TERMINAL_STATUSES
        ]

    async def count_overdue_all(self) -> int:
        now = utcnow()
        return sum(
            1 for t in self.tasks.values()
            if t.deleted_at is None and t.due_date is not None and t.due_date < now and t.status not in TERMINAL_STATUSES
        )

    async def search(self, project_id: EntityId, **kwargs) -> list[Task]:
        return await self.list_for_project(project_id, include_archived=kwargs.get("include_archived", False))

    async def add(self, task: Task) -> None:
        self.tasks[task.id] = task

    async def update(self, task: Task) -> None:
        self.tasks[task.id] = task


class FakeTaskAssignmentRepository:
    def __init__(self) -> None:
        self.assignments: list[TaskAssignment] = []

    async def get(self, task_id: EntityId, user_id: UserId) -> TaskAssignment | None:
        return next((a for a in self.assignments if a.task_id == task_id and a.user_id == user_id), None)

    async def list_for_task(self, task_id: EntityId) -> list[TaskAssignment]:
        return [a for a in self.assignments if a.task_id == task_id]

    async def list_for_user(self, user_id: UserId) -> list[TaskAssignment]:
        return [a for a in self.assignments if a.user_id == user_id]

    async def add(self, assignment: TaskAssignment) -> None:
        self.assignments.append(assignment)

    async def update(self, assignment: TaskAssignment) -> None:
        pass

    async def delete(self, assignment_id: EntityId) -> None:
        self.assignments = [a for a in self.assignments if a.id != assignment_id]


class FakeTaskAssignmentHistoryRepository:
    def __init__(self) -> None:
        self.records: list[TaskAssignmentHistoryRecord] = []

    async def add(self, record: TaskAssignmentHistoryRecord) -> None:
        self.records.append(record)

    async def list_for_task(self, task_id: EntityId) -> list[TaskAssignmentHistoryRecord]:
        return [r for r in self.records if r.task_id == task_id]


class FakeLabelRepository:
    def __init__(self) -> None:
        self.labels: dict[EntityId, Label] = {}

    async def get_by_id(self, label_id: EntityId) -> Label | None:
        return self.labels.get(label_id)

    async def get_by_name(self, project_id: EntityId, name: str) -> Label | None:
        return next((l for l in self.labels.values() if l.project_id == project_id and l.name == name), None)

    async def list_for_project(self, project_id: EntityId) -> list[Label]:
        return [l for l in self.labels.values() if l.project_id == project_id]

    async def add(self, label: Label) -> None:
        self.labels[label.id] = label

    async def update(self, label: Label) -> None:
        self.labels[label.id] = label

    async def delete(self, label_id: EntityId) -> None:
        self.labels.pop(label_id, None)


class FakeTaskLabelRepository:
    def __init__(self) -> None:
        self.task_labels: list[TaskLabel] = []

    async def get(self, task_id: EntityId, label_id: EntityId) -> TaskLabel | None:
        return next((tl for tl in self.task_labels if tl.task_id == task_id and tl.label_id == label_id), None)

    async def list_for_task(self, task_id: EntityId) -> list[TaskLabel]:
        return [tl for tl in self.task_labels if tl.task_id == task_id]

    async def list_task_ids_for_label(self, label_id: EntityId) -> list[EntityId]:
        return [tl.task_id for tl in self.task_labels if tl.label_id == label_id]

    async def add(self, task_label: TaskLabel) -> None:
        self.task_labels.append(task_label)

    async def delete(self, task_label_id: EntityId) -> None:
        self.task_labels = [tl for tl in self.task_labels if tl.id != task_label_id]


class FakeTaskDependencyRepository:
    def __init__(self) -> None:
        self.dependencies: list[TaskDependency] = []

    async def get(self, task_id: EntityId, depends_on_task_id: EntityId) -> TaskDependency | None:
        return next(
            (d for d in self.dependencies if d.task_id == task_id and d.depends_on_task_id == depends_on_task_id), None
        )

    async def list_dependencies(self, task_id: EntityId) -> list[TaskDependency]:
        return [d for d in self.dependencies if d.task_id == task_id]

    async def list_dependents(self, task_id: EntityId) -> list[TaskDependency]:
        return [d for d in self.dependencies if d.depends_on_task_id == task_id]

    async def add(self, dependency: TaskDependency) -> None:
        self.dependencies.append(dependency)

    async def delete(self, dependency_id: EntityId) -> None:
        self.dependencies = [d for d in self.dependencies if d.id != dependency_id]


class FakeTaskRelationRepository:
    def __init__(self) -> None:
        self.relations: list[TaskRelation] = []

    async def get(self, task_id: EntityId, related_task_id: EntityId) -> TaskRelation | None:
        return next(
            (r for r in self.relations if r.task_id == task_id and r.related_task_id == related_task_id), None
        )

    async def list_for_task(self, task_id: EntityId) -> list[TaskRelation]:
        return [r for r in self.relations if r.task_id == task_id]

    async def add(self, relation: TaskRelation) -> None:
        self.relations.append(relation)

    async def delete(self, relation_id: EntityId) -> None:
        self.relations = [r for r in self.relations if r.id != relation_id]


class FakeWorkflowDefinitionRepository:
    def __init__(self) -> None:
        self.workflows: dict[EntityId, WorkflowDefinition] = {}

    async def get_by_id(self, workflow_id: EntityId) -> WorkflowDefinition | None:
        return self.workflows.get(workflow_id)

    async def get_for_project(self, project_id: EntityId) -> WorkflowDefinition | None:
        return next((w for w in self.workflows.values() if w.project_id == project_id), None)

    async def add(self, workflow: WorkflowDefinition) -> None:
        self.workflows[workflow.id] = workflow

    async def update(self, workflow: WorkflowDefinition) -> None:
        self.workflows[workflow.id] = workflow


class FakeTasksAuditLogRepository:
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


class FakeTasksUnitOfWork:
    def __init__(self) -> None:
        self.tasks = FakeTaskRepository()
        self.task_assignments = FakeTaskAssignmentRepository()
        self.task_assignment_history = FakeTaskAssignmentHistoryRepository()
        self.labels = FakeLabelRepository()
        self.task_labels = FakeTaskLabelRepository()
        self.task_dependencies = FakeTaskDependencyRepository()
        self.task_relations = FakeTaskRelationRepository()
        self.workflow_definitions = FakeWorkflowDefinitionRepository()
        self.audit_logs = FakeTasksAuditLogRepository()
        self.outbox = FakeOutboxWriter()

    async def __aenter__(self) -> "FakeTasksUnitOfWork":
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


class FakeUserDirectory:
    def __init__(self, users: dict[UserId, UserSummary] | None = None) -> None:
        self.by_id = users or {}

    async def get_by_id(self, *, user_id) -> UserSummary | None:
        return self.by_id.get(user_id)
