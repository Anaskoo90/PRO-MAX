"""
Task Assignment submodule: single assignee, multiple assignees, reassign,
assignment history. An assignment history record is written on every
change — append-only, mirroring Identity's PasswordHistoryEntry convention
— giving a full audit trail of who was assigned/unassigned/reassigned and
by whom, independent of the live TaskAssignment rows.

Assignees are validated against the task's project membership (via
ProjectContextPort) — you can't assign a task to someone who isn't a
member of that project. Reuses the platform's NotificationDispatcher (same
class Identity/Projects use) to notify a newly (re)assigned user, and
UserDirectoryPort (satisfied by reusing Projects' IdentityUserDirectoryAdapter,
see composition.py) to resolve their email.
"""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import (
    NotificationChannel,
    NotificationDispatcher,
    NotificationRequest,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.tasks.application.authorization_helpers import TaskAuthorization
from app.tasks.application.dtos import TaskAssignmentDTO, TaskAssignmentHistoryDTO
from app.tasks.application.ports import OrgPermissionCheckerPort, ProjectContextPort, UserDirectoryPort
from app.tasks.domain.audit import TasksAuditEventCategory, TasksAuditLogRecord
from app.tasks.domain.entities import TaskAssignment, TaskAssignmentAction, TaskAssignmentHistoryRecord
from app.tasks.domain.events import TaskAssigned, TaskReassigned, TaskUnassigned
from app.tasks.domain.exceptions import (
    TaskAlreadyAssignedError,
    TaskAssignmentNotFoundError,
    TaskNotFoundError,
    UserNotInOrganizationError,
)


def _assignment_to_dto(a: TaskAssignment) -> TaskAssignmentDTO:
    return TaskAssignmentDTO(
        id=a.id, task_id=a.task_id, user_id=a.user_id, assigned_by=a.assigned_by, is_primary=a.is_primary,
        assigned_at=a.assigned_at,
    )


def _history_to_dto(h: TaskAssignmentHistoryRecord) -> TaskAssignmentHistoryDTO:
    return TaskAssignmentHistoryDTO(
        id=h.id, task_id=h.task_id, user_id=h.user_id, action=h.action, actor_user_id=h.actor_user_id,
        occurred_at=h.occurred_at,
    )


class TaskAssignmentService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort, notification_dispatcher: NotificationDispatcher | None = None,
        user_directory: UserDirectoryPort | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TaskAuthorization(permission_checker=permission_checker, project_context=project_context)
        self._project_context = project_context
        self._notification_dispatcher = notification_dispatcher
        self._user_directory = user_directory

    async def _notify_assignee(self, *, org_id: OrgId, user_id: UserId, task_title: str) -> None:
        if self._notification_dispatcher is None or self._user_directory is None:
            return
        user = await self._user_directory.get_by_id(user_id=user_id)
        if user is None:
            return
        await self._notification_dispatcher.dispatch(
            NotificationRequest(
                org_id=org_id, channel=NotificationChannel.EMAIL, recipient=user.email,
                subject=f"You've been assigned to '{task_title}'",
                body=f"You were assigned to the task '{task_title}'. Sign in to GuildDesk to view it.",
            )
        )

    async def assign(
        self, *, task_id: EntityId, actor_user_id: UserId, assignee_user_id: UserId, is_primary: bool = False,
    ) -> TaskAssignmentDTO:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            member = await self._project_context.get_member(project_id=task.project_id, user_id=assignee_user_id)
            if member is None or member.status != "active":
                raise UserNotInOrganizationError(str(assignee_user_id))

            if await uow.task_assignments.get(task_id, assignee_user_id) is not None:
                raise TaskAlreadyAssignedError()

            if is_primary:
                await self._clear_existing_primary(uow, task_id)

            assignment = TaskAssignment.create(task_id=task_id, user_id=assignee_user_id, assigned_by=actor_user_id, is_primary=is_primary)
            await uow.task_assignments.add(assignment)
            await uow.task_assignment_history.add(
                TaskAssignmentHistoryRecord.create(
                    task_id=task_id, user_id=assignee_user_id, action=TaskAssignmentAction.ASSIGNED, actor_user_id=actor_user_id,
                )
            )
            await uow.audit_logs.add(
                TasksAuditLogRecord.create(
                    org_id=task.org_id, category=TasksAuditEventCategory.ASSIGNMENT_CHANGE, action="task_assigned",
                    actor_user_id=actor_user_id, resource_type="task", resource_id=str(task_id),
                    metadata={"assignee_user_id": str(assignee_user_id)},
                )
            )
            await uow.commit()
            task_title, task_org_id = task.title, task.org_id
            await self._dispatcher.dispatch(TaskAssigned(aggregate_id=task_id, user_id=assignee_user_id, is_primary=is_primary))

        await self._notify_assignee(org_id=task_org_id, user_id=assignee_user_id, task_title=task_title)
        return _assignment_to_dto(assignment)

    async def _clear_existing_primary(self, uow, task_id: EntityId) -> None:
        for existing in await uow.task_assignments.list_for_task(task_id):
            if existing.is_primary:
                existing.is_primary = False
                await uow.task_assignments.update(existing)

    async def unassign(self, *, task_id: EntityId, actor_user_id: UserId, assignee_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            assignment = await uow.task_assignments.get(task_id, assignee_user_id)
            if assignment is None:
                raise TaskAssignmentNotFoundError(task_id, assignee_user_id)

            await uow.task_assignments.delete(assignment.id)
            await uow.task_assignment_history.add(
                TaskAssignmentHistoryRecord.create(
                    task_id=task_id, user_id=assignee_user_id, action=TaskAssignmentAction.UNASSIGNED, actor_user_id=actor_user_id,
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch(TaskUnassigned(aggregate_id=task_id, user_id=assignee_user_id))

    async def reassign(
        self, *, task_id: EntityId, actor_user_id: UserId, from_user_id: UserId | None, to_user_id: UserId,
    ) -> TaskAssignmentDTO:
        """Reassign: unassign the current (primary, if from_user_id is
        None) assignee and assign a new one, in a single transaction, with
        one combined history entry rather than two separate assign/
        unassign entries — the domain distinguishes "reassigned" from
        "assigned"+"unassigned" precisely so the history reads naturally."""
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            member = await self._project_context.get_member(project_id=task.project_id, user_id=to_user_id)
            if member is None or member.status != "active":
                raise UserNotInOrganizationError(str(to_user_id))

            previous_user_id = from_user_id
            if previous_user_id is None:
                existing = next((a for a in await uow.task_assignments.list_for_task(task_id) if a.is_primary), None)
                previous_user_id = existing.user_id if existing else None

            if previous_user_id is not None:
                previous_assignment = await uow.task_assignments.get(task_id, previous_user_id)
                if previous_assignment is not None:
                    await uow.task_assignments.delete(previous_assignment.id)

            new_assignment = TaskAssignment.create(task_id=task_id, user_id=to_user_id, assigned_by=actor_user_id, is_primary=True)
            if previous_user_id != to_user_id:
                await self._clear_existing_primary(uow, task_id)
            await uow.task_assignments.add(new_assignment)

            await uow.task_assignment_history.add(
                TaskAssignmentHistoryRecord.create(
                    task_id=task_id, user_id=to_user_id, action=TaskAssignmentAction.REASSIGNED, actor_user_id=actor_user_id,
                )
            )
            await uow.commit()
            task_title, task_org_id = task.title, task.org_id
            await self._dispatcher.dispatch(
                TaskReassigned(aggregate_id=task_id, previous_user_id=previous_user_id, new_user_id=to_user_id)
            )

        await self._notify_assignee(org_id=task_org_id, user_id=to_user_id, task_title=task_title)
        return _assignment_to_dto(new_assignment)

    async def list_assignments(self, *, task_id: EntityId) -> list[TaskAssignmentDTO]:
        async with self._uow_factory() as uow:
            assignments = await uow.task_assignments.list_for_task(task_id)
            return [_assignment_to_dto(a) for a in assignments]

    async def list_history(self, *, task_id: EntityId) -> list[TaskAssignmentHistoryDTO]:
        async with self._uow_factory() as uow:
            history = await uow.task_assignment_history.list_for_task(task_id)
            return [_history_to_dto(h) for h in history]
