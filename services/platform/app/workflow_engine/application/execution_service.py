"""
The core runtime: enrolling a task into a workflow, executing a manual
transition (submodule 3's create/rename/enable are config; this is the
actual state-machine move), and Workflow Automation's "Automatic
Transitions" (submodule 7) — chaining onward from the new state while any
enabled automatic transition's conditions hold, capped at a fixed depth so
a misconfigured workflow can't loop forever.

Approval decisions and checklist-item completion also live here since
they're both prerequisites a REQUIRED_APPROVAL / REQUIRED_CHECKLIST_COMPLETION
rule checks before a transition is allowed to fire.
"""

from __future__ import annotations

from datetime import datetime

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import utcnow
from app.workflow_engine.application.action_execution import ActionExecutor
from app.workflow_engine.application.authorization_helpers import WorkflowAuthorization
from app.workflow_engine.application.condition_evaluation import evaluate_conditions
from app.workflow_engine.application.dtos import WorkflowApprovalRequestDTO, WorkflowExecutionRecordDTO, WorkflowTaskStateDTO
from app.workflow_engine.application.ports import (
    BoardsContextPort,
    OrgPermissionCheckerPort,
    ProjectContextPort,
    TaskStatusRejectedError,
    TaskSummary,
    TasksContextPort,
)
from app.workflow_engine.application.rule_evaluation import RuleEvaluator
from app.workflow_engine.domain.entities import (
    ActionTriggerMode,
    ConditionType,
    PendingAutomationAction,
    WorkflowApprovalRequest,
    WorkflowChecklistCompletion,
    WorkflowExecutionRecord,
    WorkflowTaskState,
    WorkflowTransition,
)
from app.workflow_engine.domain.events import (
    ActionExecuted,
    ActionExecutionFailed,
    ActionScheduled,
    ApprovalDecided,
    ApprovalRequested,
    ChecklistItemCompleted,
    TaskEnrolledInWorkflow,
    TransitionExecuted,
)
from app.workflow_engine.domain.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    ChecklistItemNotFoundError,
    ConditionsNotMetError,
    InvalidTransitionError,
    TaskAlreadyEnrolledError,
    TaskNotAccessibleError,
    TaskNotEnrolledError,
    TransitionDisabledError,
    TransitionNotFoundError,
    WorkflowHasNoInitialStateError,
    WorkflowNotFoundError,
)

_MAX_AUTOMATIC_CHAIN_DEPTH = 10


def _task_state_to_dto(state: WorkflowTaskState) -> WorkflowTaskStateDTO:
    return WorkflowTaskStateDTO(id=state.id, workflow_id=state.workflow_id, task_id=state.task_id, current_state_id=state.current_state_id, updated_at=state.updated_at)


def _record_to_dto(record: WorkflowExecutionRecord) -> WorkflowExecutionRecordDTO:
    return WorkflowExecutionRecordDTO(
        id=record.id, workflow_id=record.workflow_id, task_id=record.task_id, transition_id=record.transition_id,
        from_state_id=record.from_state_id, to_state_id=record.to_state_id, actor_user_id=record.actor_user_id,
        reason=record.reason, occurred_at=record.occurred_at,
    )


def _approval_to_dto(a: WorkflowApprovalRequest) -> WorkflowApprovalRequestDTO:
    return WorkflowApprovalRequestDTO(
        id=a.id, transition_id=a.transition_id, task_id=a.task_id, status=a.status.value, requested_by=a.requested_by,
        requested_at=a.requested_at, decided_by=a.decided_by, decided_at=a.decided_at, reason=a.reason,
    )


class WorkflowExecutionService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort, tasks_context: TasksContextPort, boards_context: BoardsContextPort,
        rule_evaluator: RuleEvaluator, action_executor: ActionExecutor,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = WorkflowAuthorization(permission_checker=permission_checker, project_context=project_context)
        self._tasks_context = tasks_context
        self._boards_context = boards_context
        self._rule_evaluator = rule_evaluator
        self._action_executor = action_executor

    async def enroll_task(self, *, workflow_id: EntityId, task_id: EntityId, actor_user_id: UserId) -> WorkflowTaskStateDTO:
        async with self._uow_factory() as uow:
            workflow = await uow.workflows.get_by_id(workflow_id)
            if workflow is None:
                raise WorkflowNotFoundError(workflow_id)
            workflow.assert_active()
            await self._authorization.assert_can_execute(project_id=workflow.project_id, org_id=workflow.org_id, user_id=actor_user_id)

            if await uow.task_states.get(workflow_id, task_id) is not None:
                raise TaskAlreadyEnrolledError()
            initial_state = await uow.states.get_initial(workflow_id)
            if initial_state is None:
                raise WorkflowHasNoInitialStateError()

            task_state = WorkflowTaskState.create(workflow_id=workflow_id, task_id=task_id, initial_state_id=initial_state.id)
            await uow.task_states.add(task_state)
            await uow.commit()
            await self._dispatcher.dispatch(TaskEnrolledInWorkflow(aggregate_id=task_state.id, workflow_id=workflow_id, task_id=task_id, state_id=initial_state.id))
            return _task_state_to_dto(task_state)

    async def get_task_state(self, *, workflow_id: EntityId, task_id: EntityId) -> WorkflowTaskStateDTO:
        async with self._uow_factory() as uow:
            task_state = await uow.task_states.get(workflow_id, task_id)
            if task_state is None:
                raise TaskNotEnrolledError(task_id)
            return _task_state_to_dto(task_state)

    async def list_execution_history(self, *, workflow_id: EntityId, task_id: EntityId) -> list[WorkflowExecutionRecordDTO]:
        async with self._uow_factory() as uow:
            records = await uow.execution_records.list_for_task(workflow_id, task_id)
            return [_record_to_dto(r) for r in records]

    async def _needs_board_placement(self, uow, transition_id: EntityId) -> bool:
        conditions = await uow.conditions.list_for_transition(transition_id)
        return any(c.condition_type in (ConditionType.BOARD, ConditionType.SPRINT) for c in conditions)

    async def execute_transition(
        self, *, workflow_id: EntityId, task_id: EntityId, transition_id: EntityId, actor_user_id: UserId, reason: str = "",
    ) -> WorkflowTaskStateDTO:
        async with self._uow_factory() as uow:
            workflow = await uow.workflows.get_by_id(workflow_id)
            if workflow is None:
                raise WorkflowNotFoundError(workflow_id)
            workflow.assert_active()
            await self._authorization.assert_can_execute(project_id=workflow.project_id, org_id=workflow.org_id, user_id=actor_user_id)

            task_state = await uow.task_states.get(workflow_id, task_id)
            if task_state is None:
                raise TaskNotEnrolledError(task_id)

            transition = await uow.transitions.get_by_id(transition_id)
            if transition is None:
                raise TransitionNotFoundError(transition_id)
            if not transition.enabled:
                raise TransitionDisabledError(transition_id)
            if transition.from_state_id != task_state.current_state_id:
                raise InvalidTransitionError(task_state.current_state_id, transition_id)

            task_summary = await self._tasks_context.get_task(task_id=task_id)
            if task_summary is None:
                raise TaskNotAccessibleError(task_id)

            rules = await uow.rules.list_for_transition(transition_id)
            await self._rule_evaluator.evaluate_rules(
                uow, rules, task=task_summary, transition_id=transition_id, project_id=workflow.project_id,
                org_id=workflow.org_id, actor_user_id=actor_user_id,
            )

            conditions = await uow.conditions.list_for_transition(transition_id)
            board_placement = None
            if any(c.condition_type in (ConditionType.BOARD, ConditionType.SPRINT) for c in conditions):
                board_placement = await self._boards_context.get_board_placement_for_task(project_id=workflow.project_id, task_id=task_id)
            if not evaluate_conditions(conditions, task=task_summary, board_placement=board_placement):
                raise ConditionsNotMetError()

        dto = await self._apply_transition(
            workflow_id=workflow_id, org_id=task_summary.org_id, task_id=task_id, transition=transition,
            actor_user_id=actor_user_id, reason=reason,
        )
        await self._auto_advance(workflow_id=workflow_id, task_id=task_id, actor_user_id=actor_user_id)

        # Re-fetch: _auto_advance may have moved the task further than the
        # manual transition above did, and the caller should see wherever
        # the task actually landed, not the intermediate hop.
        async with self._uow_factory() as uow:
            final_state = await uow.task_states.get(workflow_id, task_id)
        return _task_state_to_dto(final_state) if final_state is not None else dto

    async def _apply_transition(
        self, *, workflow_id: EntityId, org_id: OrgId, task_id: EntityId, transition: WorkflowTransition,
        actor_user_id: UserId, reason: str,
    ) -> WorkflowTaskStateDTO:
        async with self._uow_factory() as uow:
            task_state = await uow.task_states.get(workflow_id, task_id)
            from_state_id = task_state.current_state_id
            to_state_id = transition.to_state_id
            task_state.move_to_state(to_state_id)
            await uow.task_states.update(task_state)

            to_state = await uow.states.get_by_id(to_state_id)

            record = WorkflowExecutionRecord.create(
                workflow_id=workflow_id, task_id=task_id, transition_id=transition.id, from_state_id=from_state_id,
                to_state_id=to_state_id, actor_user_id=actor_user_id, reason=reason,
            )
            await uow.execution_records.add(record)

            actions = await uow.actions.list_for_transition(transition.id)
            immediate_actions = [a for a in actions if a.trigger_mode == ActionTriggerMode.IMMEDIATE]
            deferred_actions = [a for a in actions if a.trigger_mode != ActionTriggerMode.IMMEDIATE]

            scheduled_events = []
            now = utcnow()
            for action in deferred_actions:
                run_at = action.compute_run_at(base_time=now)
                pending = PendingAutomationAction.create(
                    workflow_id=workflow_id, task_id=task_id, transition_id=transition.id, action_id=action.id,
                    run_at=run_at, actor_user_id=actor_user_id,
                )
                await uow.pending_actions.add(pending)
                scheduled_events.append(ActionScheduled(aggregate_id=pending.id, workflow_id=workflow_id, task_id=task_id, action_id=action.id, run_at=run_at))

            await uow.commit()

        await self._dispatcher.dispatch(
            TransitionExecuted(aggregate_id=transition.id, workflow_id=workflow_id, task_id=task_id, transition_id=transition.id, from_state_id=from_state_id, to_state_id=to_state_id)
        )
        await self._dispatcher.dispatch_all(scheduled_events)

        # Status sync + immediate action execution happen after the
        # transition-side transaction commits, same technique Boards uses
        # for its mapped_task_status sync — a rejected downstream call
        # doesn't undo the successful workflow state move.
        if to_state.mapped_task_status is not None:
            try:
                await self._tasks_context.change_task_status(task_id=task_id, actor_user_id=actor_user_id, status=to_state.mapped_task_status)
            except TaskStatusRejectedError:
                raise

        for action in immediate_actions:
            try:
                async with self._uow_factory() as action_uow:
                    await self._action_executor.execute(action_uow, action, workflow_id=workflow_id, task_id=task_id, org_id=org_id, actor_user_id=actor_user_id)
                    await action_uow.commit()
                await self._dispatcher.dispatch(ActionExecuted(aggregate_id=action.id, workflow_id=workflow_id, task_id=task_id, action_id=action.id, action_type=action.action_type.value))
            except Exception as exc:  # noqa: BLE001 — a failed side-effect must not fail the already-committed transition
                await self._dispatcher.dispatch(ActionExecutionFailed(aggregate_id=action.id, workflow_id=workflow_id, task_id=task_id, action_id=action.id, reason=str(exc)))

        return _task_state_to_dto(task_state)

    async def _auto_advance(self, *, workflow_id: EntityId, task_id: EntityId, actor_user_id: UserId) -> None:
        """Automatic Transitions (submodule 7): from the task's new state,
        fire the first enabled automatic transition whose conditions hold
        (rules are not evaluated for automatic transitions — those exist to
        gate a human-initiated action, which an automatic hop isn't), then
        repeat from wherever that lands, capped to avoid infinite loops."""
        for _ in range(_MAX_AUTOMATIC_CHAIN_DEPTH):
            async with self._uow_factory() as uow:
                task_state = await uow.task_states.get(workflow_id, task_id)
                if task_state is None:
                    return
                candidates = [t for t in await uow.transitions.list_from_state(task_state.current_state_id) if t.enabled and t.is_automatic]
                if not candidates:
                    return
                workflow = await uow.workflows.get_by_id(workflow_id)

            task_summary = await self._tasks_context.get_task(task_id=task_id)
            if task_summary is None:
                return

            fired = None
            for transition in candidates:
                async with self._uow_factory() as uow:
                    conditions = await uow.conditions.list_for_transition(transition.id)
                board_placement = None
                if any(c.condition_type in (ConditionType.BOARD, ConditionType.SPRINT) for c in conditions):
                    board_placement = await self._boards_context.get_board_placement_for_task(project_id=workflow.project_id, task_id=task_id)
                if evaluate_conditions(conditions, task=task_summary, board_placement=board_placement):
                    fired = transition
                    break

            if fired is None:
                return
            await self._apply_transition(workflow_id=workflow_id, org_id=workflow.org_id, task_id=task_id, transition=fired, actor_user_id=actor_user_id, reason="automatic")

    # --- Required Approval (transition rule) ---

    async def request_approval(self, *, transition_id: EntityId, task_id: EntityId, actor_user_id: UserId) -> WorkflowApprovalRequestDTO:
        async with self._uow_factory() as uow:
            transition = await uow.transitions.get_by_id(transition_id)
            if transition is None:
                raise TransitionNotFoundError(transition_id)
            approval = WorkflowApprovalRequest.create(transition_id=transition_id, task_id=task_id, requested_by=actor_user_id)
            await uow.approvals.add(approval)
            await uow.commit()
            await self._dispatcher.dispatch(ApprovalRequested(aggregate_id=approval.id, transition_id=transition_id, task_id=task_id))
            return _approval_to_dto(approval)

    async def decide_approval(self, *, approval_id: EntityId, actor_user_id: UserId, approved: bool, reason: str = "") -> WorkflowApprovalRequestDTO:
        async with self._uow_factory() as uow:
            approval = await uow.approvals.get_by_id(approval_id)
            if approval is None:
                raise ApprovalNotFoundError(approval_id)
            if approved:
                approval.approve(decided_by=actor_user_id, reason=reason)
            else:
                approval.reject(decided_by=actor_user_id, reason=reason)
            await uow.approvals.update(approval)
            await uow.commit()
            await self._dispatcher.dispatch(ApprovalDecided(aggregate_id=approval.id, transition_id=approval.transition_id, task_id=approval.task_id, decision=approval.status.value))
            return _approval_to_dto(approval)

    # --- Required Checklist Completion (transition rule) ---

    async def complete_checklist_item(self, *, item_id: EntityId, task_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            item = await uow.checklist_items.get_by_id(item_id)
            if item is None:
                raise ChecklistItemNotFoundError(item_id)
            if await uow.checklist_completions.get(item_id, task_id) is not None:
                return
            completion = WorkflowChecklistCompletion.create(checklist_item_id=item_id, task_id=task_id, completed_by=actor_user_id)
            await uow.checklist_completions.add(completion)
            await uow.commit()
            await self._dispatcher.dispatch(ChecklistItemCompleted(aggregate_id=completion.id, transition_id=item.transition_id, task_id=task_id, checklist_item_id=item_id))
