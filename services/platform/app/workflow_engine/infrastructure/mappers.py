"""ORM row <-> domain entity mapping for the Workflow Engine context."""

from __future__ import annotations

from app.workflow_engine.domain.audit import WorkflowAuditEventCategory, WorkflowAuditLogRecord
from app.workflow_engine.domain.entities import (
    ActionTriggerMode,
    ActionType,
    ActivityEntryType,
    ApprovalStatus,
    ConditionOperator,
    ConditionType,
    PendingActionStatus,
    PendingAutomationAction,
    RuleType,
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
    WorkflowStatus,
    WorkflowTaskState,
    WorkflowTransition,
)
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
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def workflow_to_domain(row: WorkflowOrmModel) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=EntityId(row.id), project_id=EntityId(row.project_id), org_id=OrgId(row.org_id), name=row.name,
        description=row.description, status=WorkflowStatus(row.status), archived_at=row.archived_at,
        deleted_at=row.deleted_at, version=row.version,
    )


def workflow_to_orm(entity: WorkflowDefinition, row: WorkflowOrmModel | None = None) -> WorkflowOrmModel:
    row = row or WorkflowOrmModel(id=entity.id)
    row.project_id = entity.project_id
    row.org_id = entity.org_id
    row.name = entity.name
    row.description = entity.description
    row.status = entity.status.value
    row.archived_at = entity.archived_at
    row.deleted_at = entity.deleted_at
    row.version = entity.version
    return row


def state_to_domain(row: WorkflowStateOrmModel) -> WorkflowState:
    return WorkflowState(
        id=EntityId(row.id), workflow_id=EntityId(row.workflow_id), name=row.name, position=row.position,
        is_initial=row.is_initial, is_final=row.is_final, is_hidden=row.is_hidden, is_archived=row.is_archived,
        mapped_task_status=row.mapped_task_status, version=row.version,
    )


def state_to_orm(entity: WorkflowState, row: WorkflowStateOrmModel | None = None) -> WorkflowStateOrmModel:
    row = row or WorkflowStateOrmModel(id=entity.id, workflow_id=entity.workflow_id)
    row.name = entity.name
    row.position = entity.position
    row.is_initial = entity.is_initial
    row.is_final = entity.is_final
    row.is_hidden = entity.is_hidden
    row.is_archived = entity.is_archived
    row.mapped_task_status = entity.mapped_task_status
    row.version = entity.version
    return row


def transition_to_domain(row: WorkflowTransitionOrmModel) -> WorkflowTransition:
    return WorkflowTransition(
        id=EntityId(row.id), workflow_id=EntityId(row.workflow_id), name=row.name,
        from_state_id=EntityId(row.from_state_id), to_state_id=EntityId(row.to_state_id), position=row.position,
        enabled=row.enabled, is_automatic=row.is_automatic, version=row.version,
    )


def transition_to_orm(entity: WorkflowTransition, row: WorkflowTransitionOrmModel | None = None) -> WorkflowTransitionOrmModel:
    row = row or WorkflowTransitionOrmModel(id=entity.id, workflow_id=entity.workflow_id, from_state_id=entity.from_state_id, to_state_id=entity.to_state_id)
    row.name = entity.name
    row.position = entity.position
    row.enabled = entity.enabled
    row.is_automatic = entity.is_automatic
    row.version = entity.version
    return row


def rule_to_domain(row: TransitionRuleOrmModel) -> TransitionRule:
    return TransitionRule(id=EntityId(row.id), transition_id=EntityId(row.transition_id), rule_type=RuleType(row.rule_type), config=row.config)


def rule_to_orm(entity: TransitionRule) -> TransitionRuleOrmModel:
    return TransitionRuleOrmModel(id=entity.id, transition_id=entity.transition_id, rule_type=entity.rule_type.value, config=entity.config)


def action_to_domain(row: WorkflowActionOrmModel) -> WorkflowAction:
    return WorkflowAction(
        id=EntityId(row.id), transition_id=EntityId(row.transition_id), action_type=ActionType(row.action_type),
        config=row.config, position=row.position, trigger_mode=ActionTriggerMode(row.trigger_mode),
        delay_seconds=row.delay_seconds, scheduled_at=row.scheduled_at,
    )


def action_to_orm(entity: WorkflowAction) -> WorkflowActionOrmModel:
    return WorkflowActionOrmModel(
        id=entity.id, transition_id=entity.transition_id, action_type=entity.action_type.value, config=entity.config,
        position=entity.position, trigger_mode=entity.trigger_mode.value, delay_seconds=entity.delay_seconds,
        scheduled_at=entity.scheduled_at,
    )


def condition_to_domain(row: WorkflowConditionOrmModel) -> WorkflowCondition:
    return WorkflowCondition(
        id=EntityId(row.id), transition_id=EntityId(row.transition_id), condition_type=ConditionType(row.condition_type),
        operator=ConditionOperator(row.operator), value=row.value.get("v"), position=row.position,
    )


def condition_to_orm(entity: WorkflowCondition) -> WorkflowConditionOrmModel:
    return WorkflowConditionOrmModel(
        id=entity.id, transition_id=entity.transition_id, condition_type=entity.condition_type.value,
        operator=entity.operator.value, value={"v": entity.value}, position=entity.position,
    )


def task_state_to_domain(row: WorkflowTaskStateOrmModel) -> WorkflowTaskState:
    return WorkflowTaskState(
        id=EntityId(row.id), workflow_id=EntityId(row.workflow_id), task_id=EntityId(row.task_id),
        current_state_id=EntityId(row.current_state_id), updated_at=row.updated_at, version=row.version,
    )


def task_state_to_orm(entity: WorkflowTaskState, row: WorkflowTaskStateOrmModel | None = None) -> WorkflowTaskStateOrmModel:
    row = row or WorkflowTaskStateOrmModel(id=entity.id, workflow_id=entity.workflow_id, task_id=entity.task_id)
    row.current_state_id = entity.current_state_id
    row.updated_at = entity.updated_at
    row.version = entity.version
    return row


def execution_record_to_domain(row: WorkflowExecutionRecordOrmModel) -> WorkflowExecutionRecord:
    return WorkflowExecutionRecord(
        id=EntityId(row.id), workflow_id=EntityId(row.workflow_id), task_id=EntityId(row.task_id),
        transition_id=EntityId(row.transition_id), from_state_id=EntityId(row.from_state_id),
        to_state_id=EntityId(row.to_state_id), actor_user_id=EntityId(row.actor_user_id), reason=row.reason,
        occurred_at=row.occurred_at,
    )


def execution_record_to_orm(entity: WorkflowExecutionRecord) -> WorkflowExecutionRecordOrmModel:
    return WorkflowExecutionRecordOrmModel(
        id=entity.id, workflow_id=entity.workflow_id, task_id=entity.task_id, transition_id=entity.transition_id,
        from_state_id=entity.from_state_id, to_state_id=entity.to_state_id, actor_user_id=entity.actor_user_id,
        reason=entity.reason, occurred_at=entity.occurred_at,
    )


def pending_action_to_domain(row: PendingAutomationActionOrmModel) -> PendingAutomationAction:
    return PendingAutomationAction(
        id=EntityId(row.id), workflow_id=EntityId(row.workflow_id), task_id=EntityId(row.task_id),
        transition_id=EntityId(row.transition_id), action_id=EntityId(row.action_id), run_at=row.run_at,
        actor_user_id=EntityId(row.actor_user_id), status=PendingActionStatus(row.status), created_at=row.created_at,
        executed_at=row.executed_at, failure_reason=row.failure_reason,
    )


def pending_action_to_orm(entity: PendingAutomationAction, row: PendingAutomationActionOrmModel | None = None) -> PendingAutomationActionOrmModel:
    row = row or PendingAutomationActionOrmModel(
        id=entity.id, workflow_id=entity.workflow_id, task_id=entity.task_id, transition_id=entity.transition_id,
        action_id=entity.action_id, run_at=entity.run_at, actor_user_id=entity.actor_user_id, created_at=entity.created_at,
    )
    row.status = entity.status.value
    row.executed_at = entity.executed_at
    row.failure_reason = entity.failure_reason
    return row


def approval_to_domain(row: WorkflowApprovalRequestOrmModel) -> WorkflowApprovalRequest:
    return WorkflowApprovalRequest(
        id=EntityId(row.id), transition_id=EntityId(row.transition_id), task_id=EntityId(row.task_id),
        requested_by=EntityId(row.requested_by), status=ApprovalStatus(row.status), requested_at=row.requested_at,
        decided_by=EntityId(row.decided_by) if row.decided_by else None, decided_at=row.decided_at, reason=row.reason,
    )


def approval_to_orm(entity: WorkflowApprovalRequest, row: WorkflowApprovalRequestOrmModel | None = None) -> WorkflowApprovalRequestOrmModel:
    row = row or WorkflowApprovalRequestOrmModel(
        id=entity.id, transition_id=entity.transition_id, task_id=entity.task_id, requested_by=entity.requested_by,
        requested_at=entity.requested_at,
    )
    row.status = entity.status.value
    row.decided_by = entity.decided_by
    row.decided_at = entity.decided_at
    row.reason = entity.reason
    return row


def checklist_item_to_domain(row: WorkflowChecklistItemOrmModel) -> WorkflowChecklistItem:
    return WorkflowChecklistItem(id=EntityId(row.id), transition_id=EntityId(row.transition_id), label=row.label, position=row.position, version=row.version)


def checklist_item_to_orm(entity: WorkflowChecklistItem, row: WorkflowChecklistItemOrmModel | None = None) -> WorkflowChecklistItemOrmModel:
    row = row or WorkflowChecklistItemOrmModel(id=entity.id, transition_id=entity.transition_id)
    row.label = entity.label
    row.position = entity.position
    row.version = entity.version
    return row


def checklist_completion_to_domain(row: WorkflowChecklistCompletionOrmModel) -> WorkflowChecklistCompletion:
    return WorkflowChecklistCompletion(
        id=EntityId(row.id), checklist_item_id=EntityId(row.checklist_item_id), task_id=EntityId(row.task_id),
        completed_by=EntityId(row.completed_by), completed_at=row.completed_at,
    )


def checklist_completion_to_orm(entity: WorkflowChecklistCompletion) -> WorkflowChecklistCompletionOrmModel:
    return WorkflowChecklistCompletionOrmModel(
        id=entity.id, checklist_item_id=entity.checklist_item_id, task_id=entity.task_id,
        completed_by=entity.completed_by, completed_at=entity.completed_at,
    )


def activity_entry_to_domain(row: WorkflowActivityEntryOrmModel) -> WorkflowActivityEntry:
    return WorkflowActivityEntry(
        id=EntityId(row.id), workflow_id=EntityId(row.workflow_id), task_id=EntityId(row.task_id),
        transition_id=EntityId(row.transition_id) if row.transition_id else None,
        entry_type=ActivityEntryType(row.entry_type), body=row.body, actor_user_id=EntityId(row.actor_user_id),
        occurred_at=row.occurred_at,
    )


def activity_entry_to_orm(entity: WorkflowActivityEntry) -> WorkflowActivityEntryOrmModel:
    return WorkflowActivityEntryOrmModel(
        id=entity.id, workflow_id=entity.workflow_id, task_id=entity.task_id, transition_id=entity.transition_id,
        entry_type=entity.entry_type.value, body=entity.body, actor_user_id=entity.actor_user_id,
        occurred_at=entity.occurred_at,
    )


def audit_log_to_domain(row: WorkflowAuditLogOrmModel) -> WorkflowAuditLogRecord:
    return WorkflowAuditLogRecord(
        id=EntityId(row.id), org_id=OrgId(row.org_id), category=WorkflowAuditEventCategory(row.category),
        action=row.action, actor_user_id=UserId(row.actor_user_id) if row.actor_user_id else None,
        resource_type=row.resource_type, resource_id=row.resource_id, metadata=row.metadata_,
        occurred_at=row.occurred_at,
    )


def audit_log_to_orm(entity: WorkflowAuditLogRecord) -> WorkflowAuditLogOrmModel:
    return WorkflowAuditLogOrmModel(
        id=entity.id, org_id=entity.org_id, category=entity.category.value, action=entity.action,
        actor_user_id=entity.actor_user_id, resource_type=entity.resource_type, resource_id=entity.resource_id,
        metadata_=entity.metadata, occurred_at=entity.occurred_at,
    )
