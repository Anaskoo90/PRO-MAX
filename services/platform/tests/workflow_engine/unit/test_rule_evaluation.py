import pytest

from app.workflow_engine.application.ports import ProjectMemberSummary, ProjectSummary, TaskSummary
from app.workflow_engine.application.rule_evaluation import RuleEvaluator
from app.workflow_engine.domain.entities import RuleType, TransitionRule, WorkflowChecklistCompletion, WorkflowChecklistItem
from app.workflow_engine.domain.exceptions import (
    ApprovalRequiredError,
    ChecklistIncompleteError,
    RequiredFieldValueNotMetError,
    RequiredPermissionNotMetError,
    RequiredRoleNotMetError,
    UnsupportedWorkflowFieldError,
)
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.workflow_engine.unit.fakes import AllowAllPermissionChecker, DenyAllPermissionChecker, FakeProjectContext, FakeWorkflowEngineUnitOfWork


def _task(**overrides) -> TaskSummary:
    defaults = dict(
        id=new_uuid7(), project_id=new_uuid7(), org_id=new_uuid7(), title="Demo", status="in_progress",
        priority="high", assignee_ids=(), label_ids=(),
    )
    defaults.update(overrides)
    return TaskSummary(**defaults)


@pytest.mark.asyncio
async def test_required_role_passes_for_matching_member() -> None:
    project_id = new_uuid7()
    actor_id = new_uuid7()
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"),
        members=[ProjectMemberSummary(user_id=actor_id, role="owner", status="active")],
    )
    evaluator = RuleEvaluator(permission_checker=AllowAllPermissionChecker(), project_context=project_context)
    rule = TransitionRule.create(transition_id=new_uuid7(), rule_type=RuleType.REQUIRED_ROLE, config={"roles": ["owner"]})
    uow = FakeWorkflowEngineUnitOfWork()

    await evaluator.evaluate_rules(uow, [rule], task=_task(), transition_id=new_uuid7(), project_id=project_id, org_id=new_uuid7(), actor_user_id=actor_id)


@pytest.mark.asyncio
async def test_required_role_fails_for_non_matching_member() -> None:
    project_id = new_uuid7()
    actor_id = new_uuid7()
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"),
        members=[ProjectMemberSummary(user_id=actor_id, role="viewer", status="active")],
    )
    evaluator = RuleEvaluator(permission_checker=AllowAllPermissionChecker(), project_context=project_context)
    rule = TransitionRule.create(transition_id=new_uuid7(), rule_type=RuleType.REQUIRED_ROLE, config={"roles": ["owner"]})
    uow = FakeWorkflowEngineUnitOfWork()

    with pytest.raises(RequiredRoleNotMetError):
        await evaluator.evaluate_rules(uow, [rule], task=_task(), transition_id=new_uuid7(), project_id=project_id, org_id=new_uuid7(), actor_user_id=actor_id)


@pytest.mark.asyncio
async def test_required_permission_fails_when_denied() -> None:
    project_context = FakeProjectContext(project=ProjectSummary(id=new_uuid7(), org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"))
    evaluator = RuleEvaluator(permission_checker=DenyAllPermissionChecker(), project_context=project_context)
    rule = TransitionRule.create(transition_id=new_uuid7(), rule_type=RuleType.REQUIRED_PERMISSION, config={"resource": "workflow", "action": "execute"})
    uow = FakeWorkflowEngineUnitOfWork()

    with pytest.raises(RequiredPermissionNotMetError):
        await evaluator.evaluate_rules(uow, [rule], task=_task(), transition_id=new_uuid7(), project_id=new_uuid7(), org_id=new_uuid7(), actor_user_id=new_uuid7())


@pytest.mark.asyncio
async def test_required_field_value_matches() -> None:
    project_context = FakeProjectContext(project=ProjectSummary(id=new_uuid7(), org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"))
    evaluator = RuleEvaluator(permission_checker=AllowAllPermissionChecker(), project_context=project_context)
    rule = TransitionRule.create(transition_id=new_uuid7(), rule_type=RuleType.REQUIRED_FIELD_VALUE, config={"field": "priority", "value": "high"})
    uow = FakeWorkflowEngineUnitOfWork()

    await evaluator.evaluate_rules(uow, [rule], task=_task(priority="high"), transition_id=new_uuid7(), project_id=new_uuid7(), org_id=new_uuid7(), actor_user_id=new_uuid7())


@pytest.mark.asyncio
async def test_required_field_value_mismatch_raises() -> None:
    project_context = FakeProjectContext(project=ProjectSummary(id=new_uuid7(), org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"))
    evaluator = RuleEvaluator(permission_checker=AllowAllPermissionChecker(), project_context=project_context)
    rule = TransitionRule.create(transition_id=new_uuid7(), rule_type=RuleType.REQUIRED_FIELD_VALUE, config={"field": "priority", "value": "low"})
    uow = FakeWorkflowEngineUnitOfWork()

    with pytest.raises(RequiredFieldValueNotMetError):
        await evaluator.evaluate_rules(uow, [rule], task=_task(priority="high"), transition_id=new_uuid7(), project_id=new_uuid7(), org_id=new_uuid7(), actor_user_id=new_uuid7())


@pytest.mark.asyncio
async def test_required_field_value_rejects_unsupported_field() -> None:
    """Honest gap: Workflow Engine can only evaluate fields Tasks actually
    exposes (status/priority/title) — anything else is a clear error, not
    a silently-fabricated pass."""
    project_context = FakeProjectContext(project=ProjectSummary(id=new_uuid7(), org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"))
    evaluator = RuleEvaluator(permission_checker=AllowAllPermissionChecker(), project_context=project_context)
    rule = TransitionRule.create(transition_id=new_uuid7(), rule_type=RuleType.REQUIRED_FIELD_VALUE, config={"field": "custom_sla_tier", "value": "gold"})
    uow = FakeWorkflowEngineUnitOfWork()

    with pytest.raises(UnsupportedWorkflowFieldError):
        await evaluator.evaluate_rules(uow, [rule], task=_task(), transition_id=new_uuid7(), project_id=new_uuid7(), org_id=new_uuid7(), actor_user_id=new_uuid7())


@pytest.mark.asyncio
async def test_required_approval_fails_without_an_approved_request() -> None:
    project_context = FakeProjectContext(project=ProjectSummary(id=new_uuid7(), org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"))
    evaluator = RuleEvaluator(permission_checker=AllowAllPermissionChecker(), project_context=project_context)
    rule = TransitionRule.create(transition_id=new_uuid7(), rule_type=RuleType.REQUIRED_APPROVAL, config={})
    uow = FakeWorkflowEngineUnitOfWork()
    task = _task()

    with pytest.raises(ApprovalRequiredError):
        await evaluator.evaluate_rules(uow, [rule], task=task, transition_id=rule.transition_id, project_id=new_uuid7(), org_id=new_uuid7(), actor_user_id=new_uuid7())


@pytest.mark.asyncio
async def test_required_checklist_completion_fails_when_items_incomplete() -> None:
    project_context = FakeProjectContext(project=ProjectSummary(id=new_uuid7(), org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"))
    evaluator = RuleEvaluator(permission_checker=AllowAllPermissionChecker(), project_context=project_context)
    transition_id = new_uuid7()
    rule = TransitionRule.create(transition_id=transition_id, rule_type=RuleType.REQUIRED_CHECKLIST_COMPLETION, config={})
    uow = FakeWorkflowEngineUnitOfWork()
    item = WorkflowChecklistItem.create(transition_id=transition_id, label="Confirm tests pass", position=1.0)
    await uow.checklist_items.add(item)
    task = _task()

    with pytest.raises(ChecklistIncompleteError):
        await evaluator.evaluate_rules(uow, [rule], task=task, transition_id=transition_id, project_id=new_uuid7(), org_id=new_uuid7(), actor_user_id=new_uuid7())


@pytest.mark.asyncio
async def test_required_checklist_completion_passes_once_all_items_completed() -> None:
    project_context = FakeProjectContext(project=ProjectSummary(id=new_uuid7(), org_id=new_uuid7(), workspace_id=new_uuid7(), status="active"))
    evaluator = RuleEvaluator(permission_checker=AllowAllPermissionChecker(), project_context=project_context)
    transition_id = new_uuid7()
    rule = TransitionRule.create(transition_id=transition_id, rule_type=RuleType.REQUIRED_CHECKLIST_COMPLETION, config={})
    uow = FakeWorkflowEngineUnitOfWork()
    item = WorkflowChecklistItem.create(transition_id=transition_id, label="Confirm tests pass", position=1.0)
    await uow.checklist_items.add(item)
    task = _task()
    completion = WorkflowChecklistCompletion.create(checklist_item_id=item.id, task_id=task.id, completed_by=new_uuid7())
    await uow.checklist_completions.add(completion)

    await evaluator.evaluate_rules(uow, [rule], task=task, transition_id=transition_id, project_id=new_uuid7(), org_id=new_uuid7(), actor_user_id=new_uuid7())
