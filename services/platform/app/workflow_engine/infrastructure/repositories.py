"""SQLAlchemy-backed implementations of the Workflow Engine repository Protocols."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow_engine.domain.audit import WorkflowAuditEventCategory, WorkflowAuditLogRecord
from app.workflow_engine.domain.entities import (
    PendingActionStatus,
    PendingAutomationAction,
    TransitionRule,
    WorkflowAction,
    WorkflowApprovalRequest,
    WorkflowChecklistCompletion,
    WorkflowChecklistItem,
    WorkflowCondition,
    WorkflowActivityEntry,
    WorkflowDefinition,
    WorkflowExecutionRecord,
    WorkflowState,
    WorkflowTaskState,
    WorkflowTransition,
)
from app.workflow_engine.infrastructure import mappers
from app.workflow_engine.infrastructure.orm_models import (
    PendingAutomationActionOrmModel,
    TransitionRuleOrmModel,
    WorkflowActionOrmModel,
    WorkflowApprovalRequestOrmModel,
    WorkflowAuditLogOrmModel,
    WorkflowChecklistCompletionOrmModel,
    WorkflowChecklistItemOrmModel,
    WorkflowConditionOrmModel,
    WorkflowActivityEntryOrmModel,
    WorkflowOrmModel,
    WorkflowExecutionRecordOrmModel,
    WorkflowStateOrmModel,
    WorkflowTaskStateOrmModel,
    WorkflowTransitionOrmModel,
)
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId


class SqlAlchemyWorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workflow_id: EntityId) -> WorkflowDefinition | None:
        row = await self._session.get(WorkflowOrmModel, workflow_id)
        return mappers.workflow_to_domain(row) if row and row.deleted_at is None else None

    async def list_for_project(self, project_id: EntityId, *, include_archived: bool = False) -> list[WorkflowDefinition]:
        stmt = select(WorkflowOrmModel).where(WorkflowOrmModel.project_id == project_id, WorkflowOrmModel.deleted_at.is_(None))
        if not include_archived:
            stmt = stmt.where(WorkflowOrmModel.status != "archived")
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.workflow_to_domain(r) for r in rows]

    async def add(self, workflow: WorkflowDefinition) -> None:
        self._session.add(mappers.workflow_to_orm(workflow))

    async def update(self, workflow: WorkflowDefinition) -> None:
        row = await self._session.get(WorkflowOrmModel, workflow.id)
        if row is None:
            raise ValueError(f"WorkflowDefinition {workflow.id} not found for update")
        if row.version != workflow.version:
            raise ConcurrencyConflictError("WorkflowDefinition", workflow.id)
        mappers.workflow_to_orm(workflow, row)
        row.version = workflow.version + 1
        workflow.version += 1


class SqlAlchemyWorkflowStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, state_id: EntityId) -> WorkflowState | None:
        row = await self._session.get(WorkflowStateOrmModel, state_id)
        return mappers.state_to_domain(row) if row else None

    async def get_by_name(self, workflow_id: EntityId, name: str) -> WorkflowState | None:
        stmt = select(WorkflowStateOrmModel).where(WorkflowStateOrmModel.workflow_id == workflow_id, WorkflowStateOrmModel.name == name)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.state_to_domain(row) if row else None

    async def get_initial(self, workflow_id: EntityId) -> WorkflowState | None:
        stmt = select(WorkflowStateOrmModel).where(WorkflowStateOrmModel.workflow_id == workflow_id, WorkflowStateOrmModel.is_initial.is_(True))
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.state_to_domain(row) if row else None

    async def list_for_workflow(self, workflow_id: EntityId) -> list[WorkflowState]:
        stmt = select(WorkflowStateOrmModel).where(WorkflowStateOrmModel.workflow_id == workflow_id).order_by(WorkflowStateOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.state_to_domain(r) for r in rows]

    async def add(self, state: WorkflowState) -> None:
        self._session.add(mappers.state_to_orm(state))

    async def update(self, state: WorkflowState) -> None:
        row = await self._session.get(WorkflowStateOrmModel, state.id)
        if row is None:
            raise ValueError(f"WorkflowState {state.id} not found for update")
        if row.version != state.version:
            raise ConcurrencyConflictError("WorkflowState", state.id)
        mappers.state_to_orm(state, row)
        row.version = state.version + 1
        state.version += 1

    async def delete(self, state_id: EntityId) -> None:
        row = await self._session.get(WorkflowStateOrmModel, state_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyWorkflowTransitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, transition_id: EntityId) -> WorkflowTransition | None:
        row = await self._session.get(WorkflowTransitionOrmModel, transition_id)
        return mappers.transition_to_domain(row) if row else None

    async def list_for_workflow(self, workflow_id: EntityId) -> list[WorkflowTransition]:
        stmt = select(WorkflowTransitionOrmModel).where(WorkflowTransitionOrmModel.workflow_id == workflow_id).order_by(WorkflowTransitionOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.transition_to_domain(r) for r in rows]

    async def list_from_state(self, from_state_id: EntityId) -> list[WorkflowTransition]:
        stmt = select(WorkflowTransitionOrmModel).where(WorkflowTransitionOrmModel.from_state_id == from_state_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.transition_to_domain(r) for r in rows]

    async def references_state(self, state_id: EntityId) -> bool:
        stmt = select(WorkflowTransitionOrmModel.id).where(
            (WorkflowTransitionOrmModel.from_state_id == state_id) | (WorkflowTransitionOrmModel.to_state_id == state_id)
        ).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def add(self, transition: WorkflowTransition) -> None:
        self._session.add(mappers.transition_to_orm(transition))

    async def update(self, transition: WorkflowTransition) -> None:
        row = await self._session.get(WorkflowTransitionOrmModel, transition.id)
        if row is None:
            raise ValueError(f"WorkflowTransition {transition.id} not found for update")
        if row.version != transition.version:
            raise ConcurrencyConflictError("WorkflowTransition", transition.id)
        mappers.transition_to_orm(transition, row)
        row.version = transition.version + 1
        transition.version += 1

    async def delete(self, transition_id: EntityId) -> None:
        row = await self._session.get(WorkflowTransitionOrmModel, transition_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyTransitionRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, rule_id: EntityId) -> TransitionRule | None:
        row = await self._session.get(TransitionRuleOrmModel, rule_id)
        return mappers.rule_to_domain(row) if row else None

    async def list_for_transition(self, transition_id: EntityId) -> list[TransitionRule]:
        stmt = select(TransitionRuleOrmModel).where(TransitionRuleOrmModel.transition_id == transition_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.rule_to_domain(r) for r in rows]

    async def add(self, rule: TransitionRule) -> None:
        self._session.add(mappers.rule_to_orm(rule))

    async def delete(self, rule_id: EntityId) -> None:
        row = await self._session.get(TransitionRuleOrmModel, rule_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyWorkflowActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, action_id: EntityId) -> WorkflowAction | None:
        row = await self._session.get(WorkflowActionOrmModel, action_id)
        return mappers.action_to_domain(row) if row else None

    async def list_for_transition(self, transition_id: EntityId) -> list[WorkflowAction]:
        stmt = select(WorkflowActionOrmModel).where(WorkflowActionOrmModel.transition_id == transition_id).order_by(WorkflowActionOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.action_to_domain(r) for r in rows]

    async def add(self, action: WorkflowAction) -> None:
        self._session.add(mappers.action_to_orm(action))

    async def delete(self, action_id: EntityId) -> None:
        row = await self._session.get(WorkflowActionOrmModel, action_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyWorkflowConditionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, condition_id: EntityId) -> WorkflowCondition | None:
        row = await self._session.get(WorkflowConditionOrmModel, condition_id)
        return mappers.condition_to_domain(row) if row else None

    async def list_for_transition(self, transition_id: EntityId) -> list[WorkflowCondition]:
        stmt = select(WorkflowConditionOrmModel).where(WorkflowConditionOrmModel.transition_id == transition_id).order_by(WorkflowConditionOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.condition_to_domain(r) for r in rows]

    async def add(self, condition: WorkflowCondition) -> None:
        self._session.add(mappers.condition_to_orm(condition))

    async def delete(self, condition_id: EntityId) -> None:
        row = await self._session.get(WorkflowConditionOrmModel, condition_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyWorkflowTaskStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, workflow_id: EntityId, task_id: EntityId) -> WorkflowTaskState | None:
        stmt = select(WorkflowTaskStateOrmModel).where(WorkflowTaskStateOrmModel.workflow_id == workflow_id, WorkflowTaskStateOrmModel.task_id == task_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.task_state_to_domain(row) if row else None

    async def list_for_task(self, task_id: EntityId) -> list[WorkflowTaskState]:
        stmt = select(WorkflowTaskStateOrmModel).where(WorkflowTaskStateOrmModel.task_id == task_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_state_to_domain(r) for r in rows]

    async def add(self, task_state: WorkflowTaskState) -> None:
        self._session.add(mappers.task_state_to_orm(task_state))

    async def update(self, task_state: WorkflowTaskState) -> None:
        row = await self._session.get(WorkflowTaskStateOrmModel, task_state.id)
        if row is None:
            raise ValueError(f"WorkflowTaskState {task_state.id} not found for update")
        if row.version != task_state.version:
            raise ConcurrencyConflictError("WorkflowTaskState", task_state.id)
        mappers.task_state_to_orm(task_state, row)
        row.version = task_state.version + 1
        task_state.version += 1


class SqlAlchemyWorkflowExecutionRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: WorkflowExecutionRecord) -> None:
        self._session.add(mappers.execution_record_to_orm(record))

    async def list_for_task(self, workflow_id: EntityId, task_id: EntityId) -> list[WorkflowExecutionRecord]:
        stmt = (
            select(WorkflowExecutionRecordOrmModel)
            .where(WorkflowExecutionRecordOrmModel.workflow_id == workflow_id, WorkflowExecutionRecordOrmModel.task_id == task_id)
            .order_by(WorkflowExecutionRecordOrmModel.occurred_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.execution_record_to_domain(r) for r in rows]


class SqlAlchemyPendingAutomationActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, pending_action_id: EntityId) -> PendingAutomationAction | None:
        row = await self._session.get(PendingAutomationActionOrmModel, pending_action_id)
        return mappers.pending_action_to_domain(row) if row else None

    async def list_due(self, *, before: datetime, status: PendingActionStatus = PendingActionStatus.PENDING) -> list[PendingAutomationAction]:
        # run_at is TIMESTAMPTZ on the wire, but the ORM column maps to a
        # timezone-naive DateTime() bind type — asyncpg rejects a tz-aware
        # Python datetime bound against that naive-typed parameter, so the
        # comparison value is stripped to naive UTC at this query boundary
        # only; utcnow() itself and every in-memory/domain use stay tz-aware.
        before_naive = before.replace(tzinfo=None) if before.tzinfo is not None else before
        stmt = select(PendingAutomationActionOrmModel).where(
            PendingAutomationActionOrmModel.run_at <= before_naive, PendingAutomationActionOrmModel.status == status.value
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.pending_action_to_domain(r) for r in rows]

    async def add(self, pending_action: PendingAutomationAction) -> None:
        self._session.add(mappers.pending_action_to_orm(pending_action))

    async def update(self, pending_action: PendingAutomationAction) -> None:
        row = await self._session.get(PendingAutomationActionOrmModel, pending_action.id)
        if row is None:
            raise ValueError(f"PendingAutomationAction {pending_action.id} not found for update")
        mappers.pending_action_to_orm(pending_action, row)


class SqlAlchemyWorkflowApprovalRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, approval_id: EntityId) -> WorkflowApprovalRequest | None:
        row = await self._session.get(WorkflowApprovalRequestOrmModel, approval_id)
        return mappers.approval_to_domain(row) if row else None

    async def get_latest_for_task(self, transition_id: EntityId, task_id: EntityId) -> WorkflowApprovalRequest | None:
        stmt = (
            select(WorkflowApprovalRequestOrmModel)
            .where(WorkflowApprovalRequestOrmModel.transition_id == transition_id, WorkflowApprovalRequestOrmModel.task_id == task_id)
            .order_by(WorkflowApprovalRequestOrmModel.requested_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.approval_to_domain(row) if row else None

    async def add(self, approval: WorkflowApprovalRequest) -> None:
        self._session.add(mappers.approval_to_orm(approval))

    async def update(self, approval: WorkflowApprovalRequest) -> None:
        row = await self._session.get(WorkflowApprovalRequestOrmModel, approval.id)
        if row is None:
            raise ValueError(f"WorkflowApprovalRequest {approval.id} not found for update")
        mappers.approval_to_orm(approval, row)


class SqlAlchemyWorkflowChecklistItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, item_id: EntityId) -> WorkflowChecklistItem | None:
        row = await self._session.get(WorkflowChecklistItemOrmModel, item_id)
        return mappers.checklist_item_to_domain(row) if row else None

    async def list_for_transition(self, transition_id: EntityId) -> list[WorkflowChecklistItem]:
        stmt = select(WorkflowChecklistItemOrmModel).where(WorkflowChecklistItemOrmModel.transition_id == transition_id).order_by(WorkflowChecklistItemOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.checklist_item_to_domain(r) for r in rows]

    async def add(self, item: WorkflowChecklistItem) -> None:
        self._session.add(mappers.checklist_item_to_orm(item))

    async def update(self, item: WorkflowChecklistItem) -> None:
        row = await self._session.get(WorkflowChecklistItemOrmModel, item.id)
        if row is None:
            raise ValueError(f"WorkflowChecklistItem {item.id} not found for update")
        mappers.checklist_item_to_orm(item, row)

    async def delete(self, item_id: EntityId) -> None:
        row = await self._session.get(WorkflowChecklistItemOrmModel, item_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyWorkflowChecklistCompletionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, checklist_item_id: EntityId, task_id: EntityId) -> WorkflowChecklistCompletion | None:
        stmt = select(WorkflowChecklistCompletionOrmModel).where(
            WorkflowChecklistCompletionOrmModel.checklist_item_id == checklist_item_id,
            WorkflowChecklistCompletionOrmModel.task_id == task_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.checklist_completion_to_domain(row) if row else None

    async def list_for_task(self, transition_id: EntityId, task_id: EntityId) -> list[WorkflowChecklistCompletion]:
        stmt = (
            select(WorkflowChecklistCompletionOrmModel)
            .join(WorkflowChecklistItemOrmModel, WorkflowChecklistItemOrmModel.id == WorkflowChecklistCompletionOrmModel.checklist_item_id)
            .where(WorkflowChecklistItemOrmModel.transition_id == transition_id, WorkflowChecklistCompletionOrmModel.task_id == task_id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.checklist_completion_to_domain(r) for r in rows]

    async def add(self, completion: WorkflowChecklistCompletion) -> None:
        self._session.add(mappers.checklist_completion_to_orm(completion))


class SqlAlchemyWorkflowActivityEntryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: WorkflowActivityEntry) -> None:
        self._session.add(mappers.activity_entry_to_orm(entry))

    async def list_for_task(self, workflow_id: EntityId, task_id: EntityId) -> list[WorkflowActivityEntry]:
        stmt = (
            select(WorkflowActivityEntryOrmModel)
            .where(WorkflowActivityEntryOrmModel.workflow_id == workflow_id, WorkflowActivityEntryOrmModel.task_id == task_id)
            .order_by(WorkflowActivityEntryOrmModel.occurred_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.activity_entry_to_domain(r) for r in rows]


class SqlAlchemyWorkflowAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: WorkflowAuditLogRecord) -> None:
        self._session.add(mappers.audit_log_to_orm(record))

    async def list_for_org(
        self, org_id: OrgId, *, category: WorkflowAuditEventCategory | None = None, limit: int = 50
    ) -> list[WorkflowAuditLogRecord]:
        stmt = select(WorkflowAuditLogOrmModel).where(WorkflowAuditLogOrmModel.org_id == org_id)
        if category is not None:
            stmt = stmt.where(WorkflowAuditLogOrmModel.category == category.value)
        stmt = stmt.order_by(WorkflowAuditLogOrmModel.occurred_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.audit_log_to_domain(r) for r in rows]
