"""SQLAlchemy ORM models for the `workflow_engine` schema — infrastructure-
layer only, per ADR-005..009 (domain layer never imports this module)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_WORKFLOW_STATUS_CHECK = "status IN ('active','archived')"
_RULE_TYPE_CHECK = (
    "rule_type IN ('required_role','required_permission','required_field_value',"
    "'required_approval','required_checklist_completion')"
)
_ACTION_TYPE_CHECK = (
    "action_type IN ('assign_user','change_priority','send_notification','create_comment',"
    "'create_activity_log','update_due_date','execute_webhook')"
)
_TRIGGER_MODE_CHECK = "trigger_mode IN ('immediate','scheduled','delayed')"
_CONDITION_TYPE_CHECK = "condition_type IN ('status','priority','label','assignee','project','board','sprint','custom_field')"
_CONDITION_OPERATOR_CHECK = "operator IN ('equals','not_equals','in','contains')"
_PENDING_STATUS_CHECK = "status IN ('pending','executed','failed','cancelled')"
_APPROVAL_STATUS_CHECK = "status IN ('pending','approved','rejected')"
_ACTIVITY_ENTRY_TYPE_CHECK = "entry_type IN ('comment','activity_log')"


class WorkflowEngineBase(DeclarativeBase):
    # See IdentityBase's identical type_annotation_map for why: bare
    # Mapped[datetime] binds as timezone-naive by default, but the actual
    # Postgres columns are TIMESTAMPTZ and utcnow() is tz-aware — this
    # closes that mismatch for every datetime column in this context.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class WorkflowOrmModel(WorkflowEngineBase):
    __tablename__ = "workflows"
    __table_args__ = (
        Index("ix_workflows_project_id", "project_id"),
        CheckConstraint(_WORKFLOW_STATUS_CHECK, name="ck_workflows_status"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    # Cross-schema references to projects.projects_table / identity.organizations
    # — not hard FKs, per the platform's standing rule for cross-context refs.
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WorkflowStateOrmModel(WorkflowEngineBase):
    __tablename__ = "workflow_states"
    __table_args__ = (
        UniqueConstraint("workflow_id", "name", name="uq_workflow_states_workflow_name"),
        Index("ix_workflow_states_workflow_id", "workflow_id"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflows.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_initial: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_final: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_hidden: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(nullable=False, default=False)
    mapped_task_status: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WorkflowTransitionOrmModel(WorkflowEngineBase):
    __tablename__ = "workflow_transitions"
    __table_args__ = (
        Index("ix_workflow_transitions_workflow_id", "workflow_id"),
        Index("ix_workflow_transitions_from_state_id", "from_state_id"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflows.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    from_state_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_states.id"), nullable=False)
    to_state_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_states.id"), nullable=False)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_automatic: Mapped[bool] = mapped_column(nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TransitionRuleOrmModel(WorkflowEngineBase):
    __tablename__ = "transition_rules"
    __table_args__ = (
        Index("ix_transition_rules_transition_id", "transition_id"),
        CheckConstraint(_RULE_TYPE_CHECK, name="ck_transition_rules_rule_type"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    transition_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class WorkflowActionOrmModel(WorkflowEngineBase):
    __tablename__ = "workflow_actions"
    __table_args__ = (
        Index("ix_workflow_actions_transition_id", "transition_id"),
        CheckConstraint(_ACTION_TYPE_CHECK, name="ck_workflow_actions_action_type"),
        CheckConstraint(_TRIGGER_MODE_CHECK, name="ck_workflow_actions_trigger_mode"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    transition_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trigger_mode: Mapped[str] = mapped_column(String, nullable=False, default="immediate")
    delay_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WorkflowConditionOrmModel(WorkflowEngineBase):
    __tablename__ = "workflow_conditions"
    __table_args__ = (
        Index("ix_workflow_conditions_transition_id", "transition_id"),
        CheckConstraint(_CONDITION_TYPE_CHECK, name="ck_workflow_conditions_condition_type"),
        CheckConstraint(_CONDITION_OPERATOR_CHECK, name="ck_workflow_conditions_operator"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    transition_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False)
    condition_type: Mapped[str] = mapped_column(String, nullable=False)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class WorkflowTaskStateOrmModel(WorkflowEngineBase):
    __tablename__ = "workflow_task_states"
    __table_args__ = (
        UniqueConstraint("workflow_id", "task_id", name="uq_workflow_task_states_workflow_task"),
        Index("ix_workflow_task_states_task_id", "task_id"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflows.id"), nullable=False)
    # Cross-schema reference to tasks.tasks_table — not a hard FK.
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    current_state_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_states.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WorkflowExecutionRecordOrmModel(WorkflowEngineBase):
    """Append-only — the Audit Trail submodule (8)."""

    __tablename__ = "workflow_execution_records"
    __table_args__ = (
        Index("ix_workflow_execution_records_workflow_task", "workflow_id", "task_id"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflows.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    transition_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False)
    from_state_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    to_state_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class PendingAutomationActionOrmModel(WorkflowEngineBase):
    __tablename__ = "pending_automation_actions"
    __table_args__ = (
        Index("ix_pending_automation_actions_run_at_status", "run_at", "status"),
        CheckConstraint(_PENDING_STATUS_CHECK, name="ck_pending_automation_actions_status"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflows.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    transition_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False)
    action_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_actions.id"), nullable=False)
    run_at: Mapped[datetime] = mapped_column(nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    executed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)


class WorkflowApprovalRequestOrmModel(WorkflowEngineBase):
    __tablename__ = "workflow_approval_requests"
    __table_args__ = (
        Index("ix_workflow_approval_requests_transition_task", "transition_id", "task_id"),
        CheckConstraint(_APPROVAL_STATUS_CHECK, name="ck_workflow_approval_requests_status"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    transition_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    requested_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reason: Mapped[str] = mapped_column(String, nullable=False, default="")


class WorkflowChecklistItemOrmModel(WorkflowEngineBase):
    __tablename__ = "workflow_checklist_items"
    __table_args__ = (
        Index("ix_workflow_checklist_items_transition_id", "transition_id"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    transition_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WorkflowChecklistCompletionOrmModel(WorkflowEngineBase):
    __tablename__ = "workflow_checklist_completions"
    __table_args__ = (
        UniqueConstraint("checklist_item_id", "task_id", name="uq_workflow_checklist_completions_item_task"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    checklist_item_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_checklist_items.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    completed_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class WorkflowActivityEntryOrmModel(WorkflowEngineBase):
    """Append-only — backs both CREATE_COMMENT and CREATE_ACTIVITY_LOG actions."""

    __tablename__ = "workflow_activity_entries"
    __table_args__ = (
        Index("ix_workflow_activity_entries_workflow_task", "workflow_id", "task_id"),
        CheckConstraint(_ACTIVITY_ENTRY_TYPE_CHECK, name="ck_workflow_activity_entries_entry_type"),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflows.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    transition_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("workflow_engine.workflow_transitions.id"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class WorkflowAuditLogOrmModel(WorkflowEngineBase):
    """Append-only — no deleted_at, no update/delete in the repository."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_workflow_audit_logs_org_id_occurred_at", "org_id", "occurred_at"),
        Index("ix_workflow_audit_logs_category", "category"),
        CheckConstraint(
            "category IN ('workflow_change','state_change','transition_change','automation_change')",
            name="ck_workflow_audit_logs_category",
        ),
        {"schema": "workflow_engine"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
