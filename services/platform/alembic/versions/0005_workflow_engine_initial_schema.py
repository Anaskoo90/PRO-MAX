"""workflow_engine initial schema

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS workflow_engine")

    op.create_table(
        "workflows",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(_WORKFLOW_STATUS_CHECK, name="ck_workflows_status"),
        schema="workflow_engine",
    )
    op.create_index("ix_workflows_project_id", "workflows", ["project_id"], schema="workflow_engine")

    op.create_table(
        "workflow_states",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflows.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_initial", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("mapped_task_status", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("workflow_id", "name", name="uq_workflow_states_workflow_name"),
        schema="workflow_engine",
    )
    op.create_index("ix_workflow_states_workflow_id", "workflow_states", ["workflow_id"], schema="workflow_engine")

    op.create_table(
        "workflow_transitions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflows.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("from_state_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_states.id"), nullable=False),
        sa.Column("to_state_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_states.id"), nullable=False),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_automatic", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema="workflow_engine",
    )
    op.create_index("ix_workflow_transitions_workflow_id", "workflow_transitions", ["workflow_id"], schema="workflow_engine")
    op.create_index("ix_workflow_transitions_from_state_id", "workflow_transitions", ["from_state_id"], schema="workflow_engine")

    op.create_table(
        "transition_rules",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("transition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("config", pg.JSONB(), nullable=False, server_default="{}"),
        sa.CheckConstraint(_RULE_TYPE_CHECK, name="ck_transition_rules_rule_type"),
        schema="workflow_engine",
    )
    op.create_index("ix_transition_rules_transition_id", "transition_rules", ["transition_id"], schema="workflow_engine")

    op.create_table(
        "workflow_actions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("transition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("config", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trigger_mode", sa.String(), nullable=False, server_default="immediate"),
        sa.Column("delay_seconds", sa.Float(), nullable=True),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(_ACTION_TYPE_CHECK, name="ck_workflow_actions_action_type"),
        sa.CheckConstraint(_TRIGGER_MODE_CHECK, name="ck_workflow_actions_trigger_mode"),
        schema="workflow_engine",
    )
    op.create_index("ix_workflow_actions_transition_id", "workflow_actions", ["transition_id"], schema="workflow_engine")

    op.create_table(
        "workflow_conditions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("transition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False),
        sa.Column("condition_type", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("value", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.CheckConstraint(_CONDITION_TYPE_CHECK, name="ck_workflow_conditions_condition_type"),
        sa.CheckConstraint(_CONDITION_OPERATOR_CHECK, name="ck_workflow_conditions_operator"),
        schema="workflow_engine",
    )
    op.create_index("ix_workflow_conditions_transition_id", "workflow_conditions", ["transition_id"], schema="workflow_engine")

    op.create_table(
        "workflow_task_states",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflows.id"), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("current_state_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_states.id"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("workflow_id", "task_id", name="uq_workflow_task_states_workflow_task"),
        schema="workflow_engine",
    )
    op.create_index("ix_workflow_task_states_task_id", "workflow_task_states", ["task_id"], schema="workflow_engine")

    op.create_table(
        "workflow_execution_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflows.id"), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("transition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False),
        sa.Column("from_state_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("to_state_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="workflow_engine",
    )
    op.create_index(
        "ix_workflow_execution_records_workflow_task", "workflow_execution_records", ["workflow_id", "task_id"],
        schema="workflow_engine",
    )

    op.create_table(
        "pending_automation_actions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflows.id"), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("transition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False),
        sa.Column("action_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_actions.id"), nullable=False),
        sa.Column("run_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.CheckConstraint(_PENDING_STATUS_CHECK, name="ck_pending_automation_actions_status"),
        schema="workflow_engine",
    )
    op.create_index(
        "ix_pending_automation_actions_run_at_status", "pending_automation_actions", ["run_at", "status"],
        schema="workflow_engine",
    )

    op.create_table(
        "workflow_approval_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("transition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("requested_by", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reason", sa.String(), nullable=False, server_default=""),
        sa.CheckConstraint(_APPROVAL_STATUS_CHECK, name="ck_workflow_approval_requests_status"),
        schema="workflow_engine",
    )
    op.create_index(
        "ix_workflow_approval_requests_transition_task", "workflow_approval_requests", ["transition_id", "task_id"],
        schema="workflow_engine",
    )

    op.create_table(
        "workflow_checklist_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("transition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_transitions.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema="workflow_engine",
    )
    op.create_index(
        "ix_workflow_checklist_items_transition_id", "workflow_checklist_items", ["transition_id"], schema="workflow_engine"
    )

    op.create_table(
        "workflow_checklist_completions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("checklist_item_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_checklist_items.id"), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("completed_by", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("checklist_item_id", "task_id", name="uq_workflow_checklist_completions_item_task"),
        schema="workflow_engine",
    )

    op.create_table(
        "workflow_activity_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflows.id"), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("transition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_engine.workflow_transitions.id"), nullable=True),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(_ACTIVITY_ENTRY_TYPE_CHECK, name="ck_workflow_activity_entries_entry_type"),
        schema="workflow_engine",
    )
    op.create_index(
        "ix_workflow_activity_entries_workflow_task", "workflow_activity_entries", ["workflow_id", "task_id"],
        schema="workflow_engine",
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "category IN ('workflow_change','state_change','transition_change','automation_change')",
            name="ck_workflow_audit_logs_category",
        ),
        schema="workflow_engine",
    )
    op.create_index("ix_workflow_audit_logs_org_id_occurred_at", "audit_logs", ["org_id", "occurred_at"], schema="workflow_engine")
    op.create_index("ix_workflow_audit_logs_category", "audit_logs", ["category"], schema="workflow_engine")

    op.create_table(
        "outbox_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="workflow_engine",
    )
    op.create_index("ix_workflow_engine_outbox_messages_published_at", "outbox_messages", ["published_at"], schema="workflow_engine")


def downgrade() -> None:
    op.drop_table("outbox_messages", schema="workflow_engine")
    op.drop_table("audit_logs", schema="workflow_engine")
    op.drop_table("workflow_activity_entries", schema="workflow_engine")
    op.drop_table("workflow_checklist_completions", schema="workflow_engine")
    op.drop_table("workflow_checklist_items", schema="workflow_engine")
    op.drop_table("workflow_approval_requests", schema="workflow_engine")
    op.drop_table("pending_automation_actions", schema="workflow_engine")
    op.drop_table("workflow_execution_records", schema="workflow_engine")
    op.drop_table("workflow_task_states", schema="workflow_engine")
    op.drop_table("workflow_conditions", schema="workflow_engine")
    op.drop_table("workflow_actions", schema="workflow_engine")
    op.drop_table("transition_rules", schema="workflow_engine")
    op.drop_table("workflow_transitions", schema="workflow_engine")
    op.drop_table("workflow_states", schema="workflow_engine")
    op.drop_table("workflows", schema="workflow_engine")
    op.execute("DROP SCHEMA IF EXISTS workflow_engine CASCADE")
