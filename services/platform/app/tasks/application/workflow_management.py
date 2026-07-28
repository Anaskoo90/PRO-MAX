"""
Task Lifecycle submodule: configurable per-project workflows. Resolution
(`resolve_workflow_for_project`) is the shared piece task_lifecycle.py
depends on — a project with no WorkflowDefinition row simply uses
DEFAULT_WORKFLOW, so most projects never need to touch this at all.
"""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId
from app.tasks.application.dtos import WorkflowDefinitionDTO
from app.tasks.application.ports import OrgPermissionCheckerPort
from app.tasks.domain.exceptions import InsufficientTaskPermissionError, WorkflowDefinitionNotFoundError
from app.tasks.domain.workflow import DEFAULT_WORKFLOW, TaskStatus, Workflow, WorkflowDefinition


async def resolve_workflow_for_project(uow, *, project_id: EntityId) -> Workflow:
    definition = await uow.workflow_definitions.get_for_project(project_id)
    return definition if definition is not None else DEFAULT_WORKFLOW


def _to_dto(workflow: WorkflowDefinition) -> WorkflowDefinitionDTO:
    return WorkflowDefinitionDTO(
        id=workflow.id, project_id=workflow.project_id, name=workflow.name,
        statuses=[s.value for s in workflow.statuses],
        transitions={k.value: [v.value for v in vs] for k, vs in workflow.transitions.items()},
    )


class WorkflowService:
    def __init__(self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._permission_checker = permission_checker

    async def _assert_can_manage_workflows(self, *, org_id, actor_user_id) -> None:
        if not await self._permission_checker.has_permission(
            user_id=actor_user_id, org_id=org_id, resource="workflow", action="manage"
        ):
            raise InsufficientTaskPermissionError(("org:workflow:manage",))

    async def create_or_replace_workflow(
        self, *, project_id: EntityId, org_id, actor_user_id, name: str, statuses: list[str],
        transitions: dict[str, list[str]],
    ) -> WorkflowDefinitionDTO:
        await self._assert_can_manage_workflows(org_id=org_id, actor_user_id=actor_user_id)

        status_tuple = tuple(TaskStatus(s) for s in statuses)
        transitions_map = {TaskStatus(k): frozenset(TaskStatus(v) for v in vs) for k, vs in transitions.items()}

        async with self._uow_factory() as uow:
            existing = await uow.workflow_definitions.get_for_project(project_id)
            if existing is None:
                workflow = WorkflowDefinition.create(project_id=project_id, name=name, statuses=status_tuple, transitions=transitions_map)
                await uow.workflow_definitions.add(workflow)
            else:
                existing.update(name=name, statuses=status_tuple, transitions=transitions_map)
                await uow.workflow_definitions.update(existing)
                workflow = existing
            events = workflow.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workflow)

    async def get_for_project(self, *, project_id: EntityId) -> WorkflowDefinitionDTO:
        async with self._uow_factory() as uow:
            workflow = await uow.workflow_definitions.get_for_project(project_id)
            if workflow is None:
                raise WorkflowDefinitionNotFoundError(project_id)
            return _to_dto(workflow)
