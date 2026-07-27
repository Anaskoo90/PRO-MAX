"""
Membership submodule: project members, invite members, remove members,
member roles.

Invites target existing organization members only (resolved by email via
UserDirectoryPort, the Anti-Corruption Layer over Identity) — inviting
someone with no GuildDesk account at all remains the platform-wide open
gap already flagged throughout Identity's delivery (no user-invitation
flow exists yet). Reuses NotificationDispatcher for the invite email,
exactly like Identity's email-verification/password-reset flows do.
"""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import (
    NotificationChannel,
    NotificationDispatcher,
    NotificationRequest,
)
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.projects.application.authorization_helpers import ProjectAuthorization
from app.projects.application.dtos import ProjectMembershipDTO
from app.projects.application.ports import OrgPermissionCheckerPort, UserDirectoryPort
from app.projects.domain.audit import ProjectsAuditEventCategory, ProjectsAuditLogRecord
from app.projects.domain.entities import ProjectMembership, ProjectRole
from app.projects.domain.events import (
    ProjectMemberInvited,
    ProjectMemberJoined,
    ProjectMemberRemoved,
    ProjectMemberRoleChanged,
)
from app.projects.domain.exceptions import (
    CannotRemoveLastProjectOwnerError,
    ProjectMembershipAlreadyExistsError,
    ProjectMembershipNotFoundError,
    ProjectNotFoundError,
    UserNotInOrganizationError,
)


def _to_dto(m: ProjectMembership) -> ProjectMembershipDTO:
    return ProjectMembershipDTO(
        id=m.id, project_id=m.project_id, user_id=m.user_id, role=m.role.value, status=m.status.value,
        invited_by=m.invited_by, invited_at=m.invited_at, joined_at=m.joined_at,
    )


class ProjectMembershipService:
    def __init__(
        self,
        *,
        uow_factory,
        dispatcher: EventDispatcher,
        notification_dispatcher: NotificationDispatcher,
        permission_checker: OrgPermissionCheckerPort,
        user_directory: UserDirectoryPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._notification_dispatcher = notification_dispatcher
        self._authorization = ProjectAuthorization(permission_checker=permission_checker)
        self._user_directory = user_directory

    async def invite_member_by_email(
        self, *, project_id: EntityId, actor_user_id: UserId, email: str, role: ProjectRole
    ) -> ProjectMembershipDTO:
        async with self._uow_factory() as uow:
            project = await uow.projects.get_by_id(project_id)
            if project is None:
                raise ProjectNotFoundError(project_id)
            await self._authorization.assert_can_manage_members(
                uow=uow, project_id=project_id, org_id=project.org_id, user_id=actor_user_id
            )

            target_user = await self._user_directory.find_by_email(org_id=project.org_id, email=email)
            if target_user is None:
                raise UserNotInOrganizationError(email)

            if await uow.project_memberships.get(project_id, UserId(target_user.id)) is not None:
                raise ProjectMembershipAlreadyExistsError()

            membership = ProjectMembership.invite(
                project_id=project_id, user_id=UserId(target_user.id), role=role, invited_by=actor_user_id
            )
            await uow.project_memberships.add(membership)
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=project.org_id, category=ProjectsAuditEventCategory.MEMBERSHIP_CHANGE,
                    action="project_member_invited", actor_user_id=actor_user_id, resource_type="project",
                    resource_id=str(project.id), metadata={"invited_user_id": str(target_user.id), "role": role.value},
                )
            )
            await uow.commit()
            # ProjectMembership is a plain join entity (no EventRecordingMixin) —
            # events are constructed and dispatched here, same convention as
            # WorkspaceService.add_member/remove_member.
            await self._dispatcher.dispatch(
                ProjectMemberInvited(aggregate_id=project_id, user_id=UserId(target_user.id), role=role.value)
            )

        await self._notification_dispatcher.dispatch(
            NotificationRequest(
                org_id=project.org_id, channel=NotificationChannel.EMAIL, recipient=target_user.email,
                subject=f"You've been invited to the project '{project.name}'",
                body=f"You were invited as {role.value} on '{project.name}'. Sign in to GuildDesk to accept.",
            )
        )
        return _to_dto(membership)

    async def accept_invite(self, *, project_id: EntityId, user_id: UserId) -> ProjectMembershipDTO:
        async with self._uow_factory() as uow:
            membership = await uow.project_memberships.get(project_id, user_id)
            if membership is None:
                raise ProjectMembershipNotFoundError(project_id, user_id)
            membership.accept()
            await uow.project_memberships.update(membership)
            await uow.commit()
            await self._dispatcher.dispatch(ProjectMemberJoined(aggregate_id=project_id, user_id=user_id))
            return _to_dto(membership)

    async def remove_member(self, *, project_id: EntityId, actor_user_id: UserId, target_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            project = await uow.projects.get_by_id(project_id)
            if project is None:
                raise ProjectNotFoundError(project_id)
            await self._authorization.assert_can_manage_members(
                uow=uow, project_id=project_id, org_id=project.org_id, user_id=actor_user_id
            )

            membership = await uow.project_memberships.get(project_id, target_user_id)
            if membership is None:
                raise ProjectMembershipNotFoundError(project_id, target_user_id)

            if membership.is_owner() and await uow.project_memberships.count_owners(project_id) <= 1:
                raise CannotRemoveLastProjectOwnerError()

            await uow.project_memberships.delete(membership.id)
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=project.org_id, category=ProjectsAuditEventCategory.MEMBERSHIP_CHANGE,
                    action="project_member_removed", actor_user_id=actor_user_id, resource_type="project",
                    resource_id=str(project.id), metadata={"removed_user_id": str(target_user_id)},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch(ProjectMemberRemoved(aggregate_id=project_id, user_id=target_user_id))

    async def change_member_role(
        self, *, project_id: EntityId, actor_user_id: UserId, target_user_id: UserId, role: ProjectRole
    ) -> ProjectMembershipDTO:
        async with self._uow_factory() as uow:
            project = await uow.projects.get_by_id(project_id)
            if project is None:
                raise ProjectNotFoundError(project_id)
            await self._authorization.assert_can_manage_members(
                uow=uow, project_id=project_id, org_id=project.org_id, user_id=actor_user_id
            )

            membership = await uow.project_memberships.get(project_id, target_user_id)
            if membership is None:
                raise ProjectMembershipNotFoundError(project_id, target_user_id)

            if membership.is_owner() and role != ProjectRole.OWNER and await uow.project_memberships.count_owners(project_id) <= 1:
                raise CannotRemoveLastProjectOwnerError()

            membership.change_role(role)
            await uow.project_memberships.update(membership)
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=project.org_id, category=ProjectsAuditEventCategory.MEMBERSHIP_CHANGE,
                    action="project_member_role_changed", actor_user_id=actor_user_id, resource_type="project",
                    resource_id=str(project.id), metadata={"target_user_id": str(target_user_id), "role": role.value},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch(
                ProjectMemberRoleChanged(aggregate_id=project_id, user_id=target_user_id, role=role.value)
            )
            return _to_dto(membership)

    async def list_members(self, *, project_id: EntityId) -> list[ProjectMembershipDTO]:
        async with self._uow_factory() as uow:
            memberships = await uow.project_memberships.list_for_project(project_id)
            return [_to_dto(m) for m in memberships]
