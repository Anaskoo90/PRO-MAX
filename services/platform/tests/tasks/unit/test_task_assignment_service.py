import pytest

from app.tasks.application.ports import ProjectMemberSummary, ProjectSummary, UserSummary
from app.tasks.application.task_assignment import TaskAssignmentService
from app.tasks.domain.entities import Task
from app.tasks.domain.exceptions import (
    TaskAlreadyAssignedError,
    TaskAssignmentNotFoundError,
    UserNotInOrganizationError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.tasks.unit.fakes import AllowAllPermissionChecker, FakeProjectContext, FakeTasksUnitOfWork, FakeUserDirectory


class _FakeEmailProvider:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, message) -> None:
        self.sent.append(message)


@pytest.fixture
def context():
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    actor_id = UserId(new_uuid7())
    member_id = UserId(new_uuid7())
    uow = FakeTasksUnitOfWork()
    task = Task.create(project_id=project_id, org_id=org_id, title="Demo")
    uow.tasks.tasks[task.id] = task
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=org_id, workspace_id=new_uuid7(), status="active"),
        members=[
            ProjectMemberSummary(user_id=actor_id, role="owner", status="active"),
            ProjectMemberSummary(user_id=member_id, role="contributor", status="active"),
        ],
    )
    return uow, project_context, task, actor_id, member_id


def _make_service(uow, project_context, user_directory=None, notification_dispatcher=None) -> TaskAssignmentService:
    return TaskAssignmentService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker(),
        project_context=project_context, notification_dispatcher=notification_dispatcher, user_directory=user_directory,
    )


@pytest.mark.asyncio
async def test_assign_creates_an_assignment_and_history_entry(context) -> None:
    uow, project_context, task, actor_id, member_id = context
    service = _make_service(uow, project_context)

    assignment = await service.assign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id, is_primary=True)

    assert assignment.user_id == member_id
    assert assignment.is_primary is True
    history = await service.list_history(task_id=task.id)
    assert len(history) == 1
    assert history[0].action == "assigned"


@pytest.mark.asyncio
async def test_assigning_a_non_member_is_rejected(context) -> None:
    uow, project_context, task, actor_id, _member_id = context
    service = _make_service(uow, project_context)
    outsider_id = UserId(new_uuid7())

    with pytest.raises(UserNotInOrganizationError):
        await service.assign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=outsider_id)


@pytest.mark.asyncio
async def test_double_assignment_is_rejected(context) -> None:
    uow, project_context, task, actor_id, member_id = context
    service = _make_service(uow, project_context)

    await service.assign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id)
    with pytest.raises(TaskAlreadyAssignedError):
        await service.assign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id)


@pytest.mark.asyncio
async def test_unassign_removes_the_assignment(context) -> None:
    uow, project_context, task, actor_id, member_id = context
    service = _make_service(uow, project_context)

    await service.assign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id)
    await service.unassign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id)

    assignments = await service.list_assignments(task_id=task.id)
    assert assignments == []


@pytest.mark.asyncio
async def test_unassigning_someone_not_assigned_raises(context) -> None:
    uow, project_context, task, actor_id, member_id = context
    service = _make_service(uow, project_context)

    with pytest.raises(TaskAssignmentNotFoundError):
        await service.unassign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id)


@pytest.mark.asyncio
async def test_reassign_moves_primary_assignment_and_records_history(context) -> None:
    uow, project_context, task, actor_id, member_id = context
    service = _make_service(uow, project_context)
    await service.assign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id, is_primary=True)

    new_assignee_id = UserId(new_uuid7())
    project_context.members.append(ProjectMemberSummary(user_id=new_assignee_id, role="contributor", status="active"))

    result = await service.reassign(task_id=task.id, actor_user_id=actor_id, from_user_id=None, to_user_id=new_assignee_id)

    assert result.user_id == new_assignee_id
    assert result.is_primary is True
    assignments = await service.list_assignments(task_id=task.id)
    assert len(assignments) == 1
    assert assignments[0].user_id == new_assignee_id

    history = await service.list_history(task_id=task.id)
    actions = [h.action for h in history]
    assert "reassigned" in actions


@pytest.mark.asyncio
async def test_assign_sends_a_notification_when_wired(context) -> None:
    uow, project_context, task, actor_id, member_id = context
    email_provider = _FakeEmailProvider()
    notification_dispatcher = NotificationDispatcher(email_provider=email_provider)
    user_directory = FakeUserDirectory({member_id: UserSummary(id=member_id, email="member@example.com", display_name="Member")})

    service = _make_service(uow, project_context, user_directory=user_directory, notification_dispatcher=notification_dispatcher)
    await service.assign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id)

    assert len(email_provider.sent) == 1
    assert email_provider.sent[0].to_address == "member@example.com"


@pytest.mark.asyncio
async def test_assign_without_notification_wiring_does_not_raise(context) -> None:
    uow, project_context, task, actor_id, member_id = context
    service = _make_service(uow, project_context)  # no notification_dispatcher/user_directory

    await service.assign(task_id=task.id, actor_user_id=actor_id, assignee_user_id=member_id)  # should not raise
