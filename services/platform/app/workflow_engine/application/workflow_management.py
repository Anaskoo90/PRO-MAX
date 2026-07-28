"""Workflow Aggregate submodule: create, update, archive, restore, delete."""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.workflow_engine.application.authorization_helpers import WorkflowAuthorization
from app.workflow_engine.application.dtos import WorkflowDTO
from app.workflow_engine.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.workflow_engine.domain.audit import WorkflowAuditEventCategory, WorkflowAuditLogRecord
from app.workflow_engine.domain.entities import WorkflowDefinition
from app.workflow_engine.domain.exceptions import InsufficientWorkflowPermissionError, WorkflowNotFoundError


def _to_dto(workflow: WorkflowDefinition) -> WorkflowDTO:
    return WorkflowDTO(
        id=workflow.id, project_id=workflow.project_id, org_id=workflow.org_id, name=workflow.name,
        description=workflow.description, status=workflow.status.value, archived_at=workflow.archived_at,
    )


class WorkflowService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = WorkflowAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def create_workflow(
        self, *, project_id: EntityId, org_id: OrgId, actor_user_id: UserId, name: str, description: str = "",
    ) -> WorkflowDTO:
        await self._authorization.assert_project_accessible(project_id=project_id, org_id=org_id)
        if not await self._authorization.can_manage(project_id=project_id, org_id=org_id, user_id=actor_user_id):
            raise InsufficientWorkflowPermissionError(("owner", "admin", "contributor"))

        async with self._uow_factory() as uow:
            workflow = WorkflowDefinition.create(project_id=project_id, org_id=org_id, name=name, description=description)
            await uow.workflows.add(workflow)
            events = workflow.pull_domain_events()
            await uow.audit_logs.add(
                WorkflowAuditLogRecord.create(
                    org_id=org_id, category=WorkflowAuditEventCategory.WORKFLOW_CHANGE, action="workflow_created",
                    actor_user_id=actor_user_id, resource_type="workflow", resource_id=str(workflow.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workflow)

    async def get(self, *, workflow_id: EntityId) -> WorkflowDTO:
        async with self._uow_factory() as uow:
            workflow = await uow.workflows.get_by_id(workflow_id)
            if workflow is None:
                raise WorkflowNotFoundError(workflow_id)
            return _to_dto(workflow)

    async def list_for_project(self, *, project_id: EntityId, include_archived: bool = False) -> list[WorkflowDTO]:
        async with self._uow_factory() as uow:
            workflows = await uow.workflows.list_for_project(project_id, include_archived=include_archived)
            return [_to_dto(w) for w in workflows]

    async def _load_and_authorize(self, uow, *, workflow_id: EntityId, actor_user_id: UserId) -> WorkflowDefinition:
        workflow = await uow.workflows.get_by_id(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(workflow_id)
        workflow.assert_not_deleted()
        await self._authorization.assert_can_manage(project_id=workflow.project_id, org_id=workflow.org_id, user_id=actor_user_id)
        return workflow

    async def update(
        self, *, workflow_id: EntityId, actor_user_id: UserId, name: str | None = None, description: str | None = None,
    ) -> WorkflowDTO:
        async with self._uow_factory() as uow:
            workflow = await self._load_and_authorize(uow, workflow_id=workflow_id, actor_user_id=actor_user_id)
            workflow.update(name=name, description=description)
            await uow.workflows.update(workflow)
            events = workflow.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workflow)

    async def archive(self, *, workflow_id: EntityId, actor_user_id: UserId) -> WorkflowDTO:
        async with self._uow_factory() as uow:
            workflow = await self._load_and_authorize(uow, workflow_id=workflow_id, actor_user_id=actor_user_id)
            workflow.archive()
            await uow.workflows.update(workflow)
            events = workflow.pull_domain_events()
            await uow.audit_logs.add(
                WorkflowAuditLogRecord.create(
                    org_id=workflow.org_id, category=WorkflowAuditEventCategory.WORKFLOW_CHANGE, action="workflow_archived",
                    actor_user_id=actor_user_id, resource_type="workflow", resource_id=str(workflow.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workflow)

    async def restore(self, *, workflow_id: EntityId, actor_user_id: UserId) -> WorkflowDTO:
        async with self._uow_factory() as uow:
            workflow = await self._load_and_authorize(uow, workflow_id=workflow_id, actor_user_id=actor_user_id)
            workflow.restore()
            await uow.workflows.update(workflow)
            events = workflow.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workflow)

    async def delete(self, *, workflow_id: EntityId, actor_user_id: UserId) -> None:
        """Soft delete (deleted_at) — distinct from archive, per the
        platform-wide convention that entity tables never hard-delete."""
        async with self._uow_factory() as uow:
            workflow = await self._load_and_authorize(uow, workflow_id=workflow_id, actor_user_id=actor_user_id)
            workflow.mark_deleted()
            await uow.workflows.update(workflow)
            events = workflow.pull_domain_events()
            await uow.audit_logs.add(
                WorkflowAuditLogRecord.create(
                    org_id=workflow.org_id, category=WorkflowAuditEventCategory.WORKFLOW_CHANGE, action="workflow_deleted",
                    actor_user_id=actor_user_id, resource_type="workflow", resource_id=str(workflow.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
