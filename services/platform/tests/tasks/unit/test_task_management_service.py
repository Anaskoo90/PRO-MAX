import pytest

from app.tasks.application.ports import ProjectMemberSummary, ProjectSummary
from app.tasks.application.task_management import TaskService
from app.tasks.domain.exceptions import ProjectNotAccessibleError, TaskNotFoundError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.tasks.unit.fakes import AllowAllPermissionChecker, DenyAllPermissionChecker, FakeProjectContext, FakeTasksUnitOfWork


def _make_service(uow, project_context, permission_checker=None) -> TaskService:
    return TaskService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(),
        permission_checker=permission_checker or AllowAllPermissionChecker(), project_context=project_context,
    )


@pytest.fixture
def context():
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    actor_id = UserId(new_uuid7())
    uow = FakeTasksUnitOfWork()
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=org_id, workspace_id=new_uuid7(), status="active"),
        members=[ProjectMemberSummary(user_id=actor_id, role="owner", status="active")],
    )
    return uow, project_context, project_id, org_id, actor_id


@pytest.mark.asyncio
async def test_create_task_succeeds_for_a_project_member(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)

    task = await service.create_task(project_id=project_id, org_id=org_id, actor_user_id=actor_id, title="Demo")

    assert task.title == "Demo"
    assert task.status == "backlog"
    assert task.priority == "medium"


@pytest.mark.asyncio
async def test_create_task_rejects_mismatched_org_id(context) -> None:
    """Tenant isolation: a caller can't create a task in another org's
    project by supplying a different org_id than the project actually
    belongs to."""
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    wrong_org_id = OrgId(new_uuid7())

    with pytest.raises(ProjectNotAccessibleError):
        await service.create_task(project_id=project_id, org_id=wrong_org_id, actor_user_id=actor_id, title="Demo")


@pytest.mark.asyncio
async def test_archive_restore_and_delete_round_trip(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    task = await service.create_task(project_id=project_id, org_id=org_id, actor_user_id=actor_id, title="Demo")

    archived = await service.archive(task_id=task.id, actor_user_id=actor_id)
    assert archived.is_archived is True

    restored = await service.restore(task_id=task.id, actor_user_id=actor_id)
    assert restored.is_archived is False

    await service.delete(task_id=task.id, actor_user_id=actor_id)
    # A soft-deleted task is invisible to get_by_id (same convention as
    # Identity's Users and Projects' Projects/Organizations), so deleting
    # it again 404s rather than surfacing "already deleted".
    with pytest.raises(TaskNotFoundError):
        await service.delete(task_id=task.id, actor_user_id=actor_id)


@pytest.mark.asyncio
async def test_duplicate_creates_a_fresh_task_with_new_id(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    original = await service.create_task(project_id=project_id, org_id=org_id, actor_user_id=actor_id, title="Original")

    duplicate = await service.duplicate(task_id=original.id, actor_user_id=actor_id)

    assert duplicate.id != original.id
    assert duplicate.title == "Original (copy)"
    assert duplicate.status == "backlog"


@pytest.mark.asyncio
async def test_non_member_cannot_create_task(context) -> None:
    uow, project_context, project_id, org_id, _actor_id = context
    outsider_id = UserId(new_uuid7())
    service = _make_service(uow, project_context, permission_checker=DenyAllPermissionChecker())

    from app.tasks.domain.exceptions import InsufficientTaskPermissionError

    with pytest.raises(InsufficientTaskPermissionError):
        await service.create_task(project_id=project_id, org_id=org_id, actor_user_id=outsider_id, title="Demo")
