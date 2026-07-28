"""Labels submodule: labels, colors, attach/detach to tasks. Filtering and
search are covered by TaskQueryService.search (TaskListFilter.label_id) —
not duplicated here."""

from __future__ import annotations

import re

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.tasks.application.authorization_helpers import TaskAuthorization
from app.tasks.application.dtos import LabelDTO
from app.tasks.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.tasks.domain.audit import TasksAuditEventCategory, TasksAuditLogRecord
from app.tasks.domain.entities import Label, TaskLabel
from app.tasks.domain.events import TaskLabelAttached, TaskLabelDetached
from app.tasks.domain.exceptions import (
    InvalidLabelColorError,
    LabelAlreadyExistsError,
    LabelNotFoundError,
    TaskLabelAlreadyAttachedError,
    TaskNotFoundError,
)

_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_color(color: str) -> str:
    if not _HEX_COLOR_PATTERN.match(color):
        raise InvalidLabelColorError(color)
    return color


def _to_dto(label: Label) -> LabelDTO:
    return LabelDTO(id=label.id, project_id=label.project_id, name=label.name, color=label.color)


class LabelService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TaskAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def create_label(self, *, project_id: EntityId, org_id, actor_user_id: UserId, name: str, color: str) -> LabelDTO:
        _validate_color(color)
        await self._authorization.assert_can_manage(project_id=project_id, org_id=org_id, user_id=actor_user_id)

        async with self._uow_factory() as uow:
            if await uow.labels.get_by_name(project_id, name) is not None:
                raise LabelAlreadyExistsError(name)
            label = Label.create(project_id=project_id, name=name, color=color)
            await uow.labels.add(label)
            events = label.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(label)

    async def update_label(
        self, *, label_id: EntityId, org_id, actor_user_id: UserId, name: str | None = None, color: str | None = None,
    ) -> LabelDTO:
        if color is not None:
            _validate_color(color)
        async with self._uow_factory() as uow:
            label = await uow.labels.get_by_id(label_id)
            if label is None:
                raise LabelNotFoundError(label_id)
            await self._authorization.assert_can_manage(project_id=label.project_id, org_id=org_id, user_id=actor_user_id)

            label.update(name=name, color=color)
            await uow.labels.update(label)
            events = label.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(label)

    async def delete_label(self, *, label_id: EntityId, org_id, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            label = await uow.labels.get_by_id(label_id)
            if label is None:
                raise LabelNotFoundError(label_id)
            await self._authorization.assert_can_manage(project_id=label.project_id, org_id=org_id, user_id=actor_user_id)

            label.mark_deleted()
            events = label.pull_domain_events()
            await uow.labels.delete(label_id)
            await uow.audit_logs.add(
                TasksAuditLogRecord.create(
                    org_id=org_id, category=TasksAuditEventCategory.LABEL_CHANGE, action="label_deleted",
                    actor_user_id=actor_user_id, resource_type="label", resource_id=str(label_id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def list_for_project(self, *, project_id: EntityId) -> list[LabelDTO]:
        async with self._uow_factory() as uow:
            labels = await uow.labels.list_for_project(project_id)
            return [_to_dto(l) for l in labels]

    async def attach_label(self, *, task_id: EntityId, label_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            label = await uow.labels.get_by_id(label_id)
            if label is None:
                raise LabelNotFoundError(label_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            if await uow.task_labels.get(task_id, label_id) is not None:
                raise TaskLabelAlreadyAttachedError()

            await uow.task_labels.add(TaskLabel.create(task_id=task_id, label_id=label_id))
            await uow.commit()
            await self._dispatcher.dispatch(TaskLabelAttached(aggregate_id=task_id, label_id=label_id))

    async def detach_label(self, *, task_id: EntityId, label_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            task_label = await uow.task_labels.get(task_id, label_id)
            if task_label is None:
                return  # detach is idempotent
            await uow.task_labels.delete(task_label.id)
            await uow.commit()
            await self._dispatcher.dispatch(TaskLabelDetached(aggregate_id=task_id, label_id=label_id))

    async def list_labels_for_task(self, *, task_id: EntityId) -> list[LabelDTO]:
        async with self._uow_factory() as uow:
            task_labels = await uow.task_labels.list_for_task(task_id)
            labels = [await uow.labels.get_by_id(tl.label_id) for tl in task_labels]
            return [_to_dto(l) for l in labels if l is not None]
