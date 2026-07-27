"""Project Templates submodule: creation, import, export, default templates."""

from __future__ import annotations

from typing import Any

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.projects.application.dtos import ProjectTemplateDTO
from app.projects.application.ports import OrgPermissionCheckerPort
from app.projects.domain.audit import ProjectsAuditEventCategory, ProjectsAuditLogRecord
from app.projects.domain.entities import ProjectTemplate, ProjectVisibility
from app.projects.domain.exceptions import (
    InsufficientProjectRoleError,
    InvalidTemplateImportError,
    ProjectTemplateNotFoundError,
)


def _to_dto(template: ProjectTemplate) -> ProjectTemplateDTO:
    return ProjectTemplateDTO(
        id=template.id, org_id=template.org_id, name=template.name, description=template.description,
        is_default=template.is_default, default_visibility=template.default_visibility.value,
        default_metadata=template.default_metadata, default_settings=template.default_settings,
    )


class ProjectTemplateService:
    def __init__(self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._permission_checker = permission_checker

    async def _assert_can_manage_templates(self, *, org_id: OrgId, actor_user_id: UserId) -> None:
        if not await self._permission_checker.has_permission(
            user_id=actor_user_id, org_id=org_id, resource="project_template", action="create"
        ):
            raise InsufficientProjectRoleError(("org:project_template:create",))

    async def create_template(
        self,
        *,
        org_id: OrgId,
        actor_user_id: UserId,
        name: str,
        description: str = "",
        default_visibility: ProjectVisibility = ProjectVisibility.WORKSPACE,
        default_metadata: dict[str, Any] | None = None,
        default_settings: dict[str, Any] | None = None,
    ) -> ProjectTemplateDTO:
        await self._assert_can_manage_templates(org_id=org_id, actor_user_id=actor_user_id)

        async with self._uow_factory() as uow:
            template = ProjectTemplate.create(
                org_id=org_id, name=name, description=description, default_visibility=default_visibility,
                default_metadata=default_metadata, default_settings=default_settings,
            )
            await uow.project_templates.add(template)
            events = template.pull_domain_events()
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=org_id, category=ProjectsAuditEventCategory.TEMPLATE_CHANGE, action="template_created",
                    actor_user_id=actor_user_id, resource_type="project_template", resource_id=str(template.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(template)

    async def import_template(self, *, org_id: OrgId, actor_user_id: UserId, data: dict[str, Any]) -> ProjectTemplateDTO:
        await self._assert_can_manage_templates(org_id=org_id, actor_user_id=actor_user_id)

        if "name" not in data or not isinstance(data["name"], str) or not data["name"].strip():
            raise InvalidTemplateImportError("missing or empty 'name' field")
        if data.get("schema_version") not in (None, 1):
            raise InvalidTemplateImportError(f"unsupported schema_version {data.get('schema_version')!r}")

        async with self._uow_factory() as uow:
            try:
                template = ProjectTemplate.from_import_dict(org_id=org_id, data=data)
            except (KeyError, ValueError) as exc:
                raise InvalidTemplateImportError(str(exc)) from exc

            await uow.project_templates.add(template)
            events = template.pull_domain_events()
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=org_id, category=ProjectsAuditEventCategory.TEMPLATE_CHANGE, action="template_imported",
                    actor_user_id=actor_user_id, resource_type="project_template", resource_id=str(template.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(template)

    async def export_template(self, *, template_id: EntityId) -> dict[str, Any]:
        async with self._uow_factory() as uow:
            template = await uow.project_templates.get_by_id(template_id)
            if template is None:
                raise ProjectTemplateNotFoundError(template_id)
            return template.to_export_dict()

    async def update_template(
        self, *, template_id: EntityId, actor_user_id: UserId, name: str | None, description: str | None
    ) -> ProjectTemplateDTO:
        async with self._uow_factory() as uow:
            template = await uow.project_templates.get_by_id(template_id)
            if template is None:
                raise ProjectTemplateNotFoundError(template_id)
            await self._assert_can_manage_templates(org_id=template.org_id, actor_user_id=actor_user_id)

            template.update(name=name, description=description)
            await uow.project_templates.update(template)
            events = template.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(template)

    async def set_default(self, *, template_id: EntityId, actor_user_id: UserId) -> ProjectTemplateDTO:
        """Default Templates: at most one default per organization —
        unmarking the previous default happens in the same transaction."""
        async with self._uow_factory() as uow:
            template = await uow.project_templates.get_by_id(template_id)
            if template is None:
                raise ProjectTemplateNotFoundError(template_id)
            await self._assert_can_manage_templates(org_id=template.org_id, actor_user_id=actor_user_id)

            events = []
            previous_default = await uow.project_templates.get_default(template.org_id)
            if previous_default is not None and previous_default.id != template.id:
                previous_default.unmark_default()
                await uow.project_templates.update(previous_default)
                events.extend(previous_default.pull_domain_events())

            template.mark_default()
            await uow.project_templates.update(template)
            events.extend(template.pull_domain_events())
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(template)

    async def delete_template(self, *, template_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            template = await uow.project_templates.get_by_id(template_id)
            if template is None:
                raise ProjectTemplateNotFoundError(template_id)
            await self._assert_can_manage_templates(org_id=template.org_id, actor_user_id=actor_user_id)

            template.mark_deleted()
            events = template.pull_domain_events()
            await uow.project_templates.delete(template_id)
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=template.org_id, category=ProjectsAuditEventCategory.TEMPLATE_CHANGE, action="template_deleted",
                    actor_user_id=actor_user_id, resource_type="project_template", resource_id=str(template.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def list_for_org(self, *, org_id: OrgId) -> list[ProjectTemplateDTO]:
        async with self._uow_factory() as uow:
            templates = await uow.project_templates.list_for_org(org_id)
            return [_to_dto(t) for t in templates]
