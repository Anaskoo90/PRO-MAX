"""
Workflow Automation submodule (7): Scheduled Actions, Delayed Actions.

`run_due_actions` is the job body registered with Platform Core's
JobScheduler in composition.py (the same infra pattern Tasks introduced
for its overdue-scan job and Boards reused for its burndown snapshot) —
scans PendingAutomationAction rows whose run_at has passed and executes
them via the same ActionExecutor the immediate-execution path uses, so a
delayed "send notification" behaves identically to an immediate one.
"""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.logger import get_logger
from app.platform_core.shared_kernel.utils import utcnow
from app.workflow_engine.application.action_execution import ActionExecutor
from app.workflow_engine.domain.events import ActionExecuted, ActionExecutionFailed

_logger = get_logger("workflow_engine.automation_service")


class WorkflowAutomationService:
    def __init__(self, *, uow_factory, dispatcher: EventDispatcher, action_executor: ActionExecutor) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._action_executor = action_executor

    async def run_due_actions(self) -> int:
        """Job body: executes every PENDING action whose run_at has
        passed. Returns the count actually processed (executed or failed)."""
        now = utcnow()
        async with self._uow_factory() as uow:
            due = await uow.pending_actions.list_due(before=now)

        processed = 0
        for pending in due:
            async with self._uow_factory() as uow:
                action = await uow.actions.get_by_id(pending.action_id)
                workflow = await uow.workflows.get_by_id(pending.workflow_id)
                if action is None or workflow is None:
                    pending.mark_failed("Action or workflow no longer exists")
                    await uow.pending_actions.update(pending)
                    await uow.commit()
                    processed += 1
                    continue
                try:
                    await self._action_executor.execute(
                        uow, action, workflow_id=pending.workflow_id, task_id=pending.task_id, org_id=workflow.org_id,
                        actor_user_id=pending.actor_user_id,
                    )
                    pending.mark_executed()
                    await uow.pending_actions.update(pending)
                    await uow.commit()
                    await self._dispatcher.dispatch(ActionExecuted(aggregate_id=action.id, workflow_id=pending.workflow_id, task_id=pending.task_id, action_id=action.id, action_type=action.action_type.value))
                except Exception as exc:  # noqa: BLE001 — one bad action must not stop the batch
                    await uow.rollback()
                    async with self._uow_factory() as failure_uow:
                        pending.mark_failed(str(exc))
                        await failure_uow.pending_actions.update(pending)
                        await failure_uow.commit()
                    await self._dispatcher.dispatch(ActionExecutionFailed(aggregate_id=action.id, workflow_id=pending.workflow_id, task_id=pending.task_id, action_id=action.id, reason=str(exc)))
                    await _logger.awarning("workflow_pending_action_failed", pending_action_id=str(pending.id), reason=str(exc))
                processed += 1
        return processed
