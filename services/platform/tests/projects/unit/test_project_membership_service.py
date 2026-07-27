import pytest

from app.projects.application.membership_management import ProjectMembershipService
from app.projects.application.ports import UserSummary
from app.projects.domain.entities import Project, ProjectMembership, ProjectRole
from app.projects.domain.exceptions import (
    CannotRemoveLastProjectOwnerError,
    ProjectMembershipAlreadyExistsError,
    UserNotInOrganizationError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.projects.unit.fakes import AllowAllPermissionChecker, FakeProjectsUnitOfWork, FakeUserDirectory


class _FakeEmailProvider:
    """No real email provider is wired anywhere in this platform yet
    (Notification Center channel providers are a standing gap) — this
    stub isolates membership-invite logic from that unrelated gap."""

    def __init__(self) -> None:
        self.sent = []

    async def send(self, message) -> None:
        self.sent.append(message)


def _make_service(uow: FakeProjectsUnitOfWork, user_directory: FakeUserDirectory) -> ProjectMembershipService:
    return ProjectMembershipService(
        uow_factory=lambda: uow,
        dispatcher=EventDispatcher(),
        notification_dispatcher=NotificationDispatcher(email_provider=_FakeEmailProvider()),
        permission_checker=AllowAllPermissionChecker(),
        user_directory=user_directory,
    )


async def _seed_project_with_owner(uow: FakeProjectsUnitOfWork, *, owner_id: UserId) -> Project:
    project = Project.create(workspace_id=EntityId(new_uuid7()), org_id=OrgId(new_uuid7()), name="Demo")
    await uow.projects.add(project)
    await uow.project_memberships.add(ProjectMembership.add_directly(project_id=project.id, user_id=owner_id, role=ProjectRole.OWNER))
    return project


@pytest.mark.asyncio
async def test_invite_member_by_email_creates_pending_membership() -> None:
    uow = FakeProjectsUnitOfWork()
    owner_id = UserId(new_uuid7())
    project = await _seed_project_with_owner(uow, owner_id=owner_id)

    invitee_id = UserId(new_uuid7())
    directory = FakeUserDirectory({"newperson@example.com": UserSummary(id=invitee_id, email="newperson@example.com", display_name="New Person")})
    service = _make_service(uow, directory)

    membership = await service.invite_member_by_email(
        project_id=project.id, actor_user_id=owner_id, email="newperson@example.com", role=ProjectRole.CONTRIBUTOR
    )

    assert membership.status == "invited"
    assert membership.role == "contributor"


@pytest.mark.asyncio
async def test_invite_unknown_email_raises() -> None:
    uow = FakeProjectsUnitOfWork()
    owner_id = UserId(new_uuid7())
    project = await _seed_project_with_owner(uow, owner_id=owner_id)
    service = _make_service(uow, FakeUserDirectory())

    with pytest.raises(UserNotInOrganizationError):
        await service.invite_member_by_email(
            project_id=project.id, actor_user_id=owner_id, email="ghost@example.com", role=ProjectRole.VIEWER
        )


@pytest.mark.asyncio
async def test_invite_existing_member_raises() -> None:
    uow = FakeProjectsUnitOfWork()
    owner_id = UserId(new_uuid7())
    project = await _seed_project_with_owner(uow, owner_id=owner_id)

    directory = FakeUserDirectory({"owner@example.com": UserSummary(id=owner_id, email="owner@example.com", display_name="Owner")})
    service = _make_service(uow, directory)

    with pytest.raises(ProjectMembershipAlreadyExistsError):
        await service.invite_member_by_email(
            project_id=project.id, actor_user_id=owner_id, email="owner@example.com", role=ProjectRole.VIEWER
        )


@pytest.mark.asyncio
async def test_removing_the_last_owner_is_rejected() -> None:
    uow = FakeProjectsUnitOfWork()
    owner_id = UserId(new_uuid7())
    project = await _seed_project_with_owner(uow, owner_id=owner_id)
    service = _make_service(uow, FakeUserDirectory())

    with pytest.raises(CannotRemoveLastProjectOwnerError):
        await service.remove_member(project_id=project.id, actor_user_id=owner_id, target_user_id=owner_id)


@pytest.mark.asyncio
async def test_removing_one_of_two_owners_succeeds() -> None:
    uow = FakeProjectsUnitOfWork()
    owner_id = UserId(new_uuid7())
    project = await _seed_project_with_owner(uow, owner_id=owner_id)

    second_owner_id = UserId(new_uuid7())
    await uow.project_memberships.add(
        ProjectMembership.add_directly(project_id=project.id, user_id=second_owner_id, role=ProjectRole.OWNER)
    )
    service = _make_service(uow, FakeUserDirectory())

    await service.remove_member(project_id=project.id, actor_user_id=owner_id, target_user_id=second_owner_id)

    remaining = await uow.project_memberships.list_for_project(project.id)
    assert len(remaining) == 1
    assert remaining[0].user_id == owner_id


@pytest.mark.asyncio
async def test_demoting_the_last_owner_is_rejected() -> None:
    uow = FakeProjectsUnitOfWork()
    owner_id = UserId(new_uuid7())
    project = await _seed_project_with_owner(uow, owner_id=owner_id)
    service = _make_service(uow, FakeUserDirectory())

    with pytest.raises(CannotRemoveLastProjectOwnerError):
        await service.change_member_role(
            project_id=project.id, actor_user_id=owner_id, target_user_id=owner_id, role=ProjectRole.ADMIN
        )
