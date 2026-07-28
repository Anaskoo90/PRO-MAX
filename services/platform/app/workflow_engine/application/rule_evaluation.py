"""
Transition Rules submodule (4): Required Role, Required Permission,
Required Field Values, Required Approval, Required Checklist Completion.

Unlike condition_evaluation.py, rule evaluation needs repository access
(approvals, checklist completions) and the two authorization ACLs, so it's
a small stateful evaluator rather than a pure function — constructed once
in composition.py and shared by execution_service.py.
"""

from __future__ import annotations

from app.workflow_engine.application.ports import OrgPermissionCheckerPort, ProjectContextPort, TaskSummary
from app.workflow_engine.domain.entities import RuleType, TransitionRule
from app.workflow_engine.domain.exceptions import (
    ApprovalRequiredError,
    ChecklistIncompleteError,
    RequiredFieldValueNotMetError,
    RequiredPermissionNotMetError,
    RequiredRoleNotMetError,
    UnsupportedWorkflowFieldError,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId

_SUPPORTED_FIELDS = frozenset({"status", "priority", "title"})


class RuleEvaluator:
    def __init__(self, *, permission_checker: OrgPermissionCheckerPort, project_context: ProjectContextPort) -> None:
        self._permission_checker = permission_checker
        self._project_context = project_context

    async def evaluate_rules(
        self, uow, rules: list[TransitionRule], *, task: TaskSummary, transition_id: EntityId, project_id: EntityId,
        org_id: OrgId, actor_user_id: UserId,
    ) -> None:
        for rule in rules:
            await self._evaluate_one(uow, rule, task=task, transition_id=transition_id, project_id=project_id, org_id=org_id, actor_user_id=actor_user_id)

    async def _evaluate_one(
        self, uow, rule: TransitionRule, *, task: TaskSummary, transition_id: EntityId, project_id: EntityId,
        org_id: OrgId, actor_user_id: UserId,
    ) -> None:
        if rule.rule_type == RuleType.REQUIRED_ROLE:
            required_roles: tuple[str, ...] = tuple(rule.config.get("roles", ()))
            member = await self._project_context.get_member(project_id=project_id, user_id=actor_user_id)
            if member is None or member.status != "active" or member.role not in required_roles:
                raise RequiredRoleNotMetError(required_roles)

        elif rule.rule_type == RuleType.REQUIRED_PERMISSION:
            resource = rule.config.get("resource", "")
            action = rule.config.get("action", "")
            if not await self._permission_checker.has_permission(user_id=actor_user_id, org_id=org_id, resource=resource, action=action):
                raise RequiredPermissionNotMetError(resource, action)

        elif rule.rule_type == RuleType.REQUIRED_FIELD_VALUE:
            field_name = rule.config.get("field", "")
            if field_name not in _SUPPORTED_FIELDS:
                raise UnsupportedWorkflowFieldError(field_name)
            expected = rule.config.get("value")
            actual = getattr(task, field_name)
            if str(actual) != str(expected):
                raise RequiredFieldValueNotMetError(field_name, expected)

        elif rule.rule_type == RuleType.REQUIRED_APPROVAL:
            approval = await uow.approvals.get_latest_for_task(transition_id, task.id)
            if approval is None or approval.status.value != "approved":
                raise ApprovalRequiredError()

        elif rule.rule_type == RuleType.REQUIRED_CHECKLIST_COMPLETION:
            items = await uow.checklist_items.list_for_transition(transition_id)
            completions = await uow.checklist_completions.list_for_task(transition_id, task.id)
            completed_item_ids = {c.checklist_item_id for c in completions}
            remaining = sum(1 for item in items if item.id not in completed_item_ids)
            if remaining > 0:
                raise ChecklistIncompleteError(remaining)
