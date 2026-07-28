"""Unit of Work for the `tasks` schema — one AsyncSession per request/
command, one commit, identical shape to Identity's/Projects' UnitOfWork."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.tasks.infrastructure.outbox import SqlAlchemyOutboxWriter
from app.tasks.infrastructure.repositories import (
    SqlAlchemyLabelRepository,
    SqlAlchemyTaskAssignmentHistoryRepository,
    SqlAlchemyTaskAssignmentRepository,
    SqlAlchemyTaskDependencyRepository,
    SqlAlchemyTaskLabelRepository,
    SqlAlchemyTaskRelationRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyTasksAuditLogRepository,
    SqlAlchemyWorkflowDefinitionRepository,
)


class TasksUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.tasks: SqlAlchemyTaskRepository | None = None
        self.task_assignments: SqlAlchemyTaskAssignmentRepository | None = None
        self.task_assignment_history: SqlAlchemyTaskAssignmentHistoryRepository | None = None
        self.labels: SqlAlchemyLabelRepository | None = None
        self.task_labels: SqlAlchemyTaskLabelRepository | None = None
        self.task_dependencies: SqlAlchemyTaskDependencyRepository | None = None
        self.task_relations: SqlAlchemyTaskRelationRepository | None = None
        self.workflow_definitions: SqlAlchemyWorkflowDefinitionRepository | None = None
        self.audit_logs: SqlAlchemyTasksAuditLogRepository | None = None
        self.outbox: SqlAlchemyOutboxWriter | None = None

    async def __aenter__(self) -> "TasksUnitOfWork":
        self.session = self._session_factory()
        self.tasks = SqlAlchemyTaskRepository(self.session)
        self.task_assignments = SqlAlchemyTaskAssignmentRepository(self.session)
        self.task_assignment_history = SqlAlchemyTaskAssignmentHistoryRepository(self.session)
        self.labels = SqlAlchemyLabelRepository(self.session)
        self.task_labels = SqlAlchemyTaskLabelRepository(self.session)
        self.task_dependencies = SqlAlchemyTaskDependencyRepository(self.session)
        self.task_relations = SqlAlchemyTaskRelationRepository(self.session)
        self.workflow_definitions = SqlAlchemyWorkflowDefinitionRepository(self.session)
        self.audit_logs = SqlAlchemyTasksAuditLogRepository(self.session)
        self.outbox = SqlAlchemyOutboxWriter(self.session, event_type="tasks.integration_event")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self.session is not None
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()

    async def rollback(self) -> None:
        assert self.session is not None
        await self.session.rollback()
