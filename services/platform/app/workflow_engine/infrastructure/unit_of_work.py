"""Unit of Work for the `workflow_engine` schema — one AsyncSession per
request/command, one commit, identical shape to every other context's
UnitOfWork."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.workflow_engine.infrastructure.outbox import SqlAlchemyOutboxWriter
from app.workflow_engine.infrastructure.repositories import (
    SqlAlchemyPendingAutomationActionRepository,
    SqlAlchemyTransitionRuleRepository,
    SqlAlchemyWorkflowActionRepository,
    SqlAlchemyWorkflowApprovalRequestRepository,
    SqlAlchemyWorkflowAuditLogRepository,
    SqlAlchemyWorkflowChecklistCompletionRepository,
    SqlAlchemyWorkflowChecklistItemRepository,
    SqlAlchemyWorkflowConditionRepository,
    SqlAlchemyWorkflowActivityEntryRepository,
    SqlAlchemyWorkflowRepository,
    SqlAlchemyWorkflowExecutionRecordRepository,
    SqlAlchemyWorkflowStateRepository,
    SqlAlchemyWorkflowTaskStateRepository,
    SqlAlchemyWorkflowTransitionRepository,
)


class WorkflowEngineUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.workflows: SqlAlchemyWorkflowRepository | None = None
        self.states: SqlAlchemyWorkflowStateRepository | None = None
        self.transitions: SqlAlchemyWorkflowTransitionRepository | None = None
        self.rules: SqlAlchemyTransitionRuleRepository | None = None
        self.actions: SqlAlchemyWorkflowActionRepository | None = None
        self.conditions: SqlAlchemyWorkflowConditionRepository | None = None
        self.task_states: SqlAlchemyWorkflowTaskStateRepository | None = None
        self.execution_records: SqlAlchemyWorkflowExecutionRecordRepository | None = None
        self.pending_actions: SqlAlchemyPendingAutomationActionRepository | None = None
        self.approvals: SqlAlchemyWorkflowApprovalRequestRepository | None = None
        self.checklist_items: SqlAlchemyWorkflowChecklistItemRepository | None = None
        self.checklist_completions: SqlAlchemyWorkflowChecklistCompletionRepository | None = None
        self.activity_entries: SqlAlchemyWorkflowActivityEntryRepository | None = None
        self.audit_logs: SqlAlchemyWorkflowAuditLogRepository | None = None
        self.outbox: SqlAlchemyOutboxWriter | None = None

    async def __aenter__(self) -> "WorkflowEngineUnitOfWork":
        self.session = self._session_factory()
        self.workflows = SqlAlchemyWorkflowRepository(self.session)
        self.states = SqlAlchemyWorkflowStateRepository(self.session)
        self.transitions = SqlAlchemyWorkflowTransitionRepository(self.session)
        self.rules = SqlAlchemyTransitionRuleRepository(self.session)
        self.actions = SqlAlchemyWorkflowActionRepository(self.session)
        self.conditions = SqlAlchemyWorkflowConditionRepository(self.session)
        self.task_states = SqlAlchemyWorkflowTaskStateRepository(self.session)
        self.execution_records = SqlAlchemyWorkflowExecutionRecordRepository(self.session)
        self.pending_actions = SqlAlchemyPendingAutomationActionRepository(self.session)
        self.approvals = SqlAlchemyWorkflowApprovalRequestRepository(self.session)
        self.checklist_items = SqlAlchemyWorkflowChecklistItemRepository(self.session)
        self.checklist_completions = SqlAlchemyWorkflowChecklistCompletionRepository(self.session)
        self.activity_entries = SqlAlchemyWorkflowActivityEntryRepository(self.session)
        self.audit_logs = SqlAlchemyWorkflowAuditLogRepository(self.session)
        self.outbox = SqlAlchemyOutboxWriter(self.session, event_type="workflow_engine.integration_event")
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
