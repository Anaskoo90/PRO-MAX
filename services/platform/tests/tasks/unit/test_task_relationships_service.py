import pytest

from app.tasks.application.ports import ProjectMemberSummary, ProjectSummary
from app.tasks.application.task_relationships import TaskRelationshipService
from app.tasks.domain.entities import Task
from app.tasks.domain.exceptions import (
    TaskCannotBeOwnParentError,
    TaskCannotDependOnItselfError,
    TaskDependencyAlreadyExistsError,
    TaskDependencyCycleError,
    TaskParentCycleError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.tasks.unit.fakes import AllowAllPermissionChecker, FakeProjectContext, FakeTasksUnitOfWork


def _make_service(uow: FakeTasksUnitOfWork, project_context: FakeProjectContext) -> TaskRelationshipService:
    return TaskRelationshipService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker(),
        project_context=project_context,
    )


def _seed_task(uow: FakeTasksUnitOfWork, *, project_id: EntityId, org_id: OrgId) -> Task:
    task = Task.create(project_id=project_id, org_id=org_id, title="Demo")
    uow.tasks.tasks[task.id] = task
    return task


@pytest.fixture
def context() -> tuple[FakeTasksUnitOfWork, FakeProjectContext, EntityId, OrgId, UserId]:
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
async def test_set_parent_succeeds_for_a_simple_case(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    parent = _seed_task(uow, project_id=project_id, org_id=org_id)
    child = _seed_task(uow, project_id=project_id, org_id=org_id)

    service = _make_service(uow, project_context)
    result = await service.set_parent(task_id=child.id, actor_user_id=actor_id, parent_task_id=parent.id)

    assert result.parent_task_id == parent.id


@pytest.mark.asyncio
async def test_set_parent_to_self_raises(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    task = _seed_task(uow, project_id=project_id, org_id=org_id)
    service = _make_service(uow, project_context)

    with pytest.raises(TaskCannotBeOwnParentError):
        await service.set_parent(task_id=task.id, actor_user_id=actor_id, parent_task_id=task.id)


@pytest.mark.asyncio
async def test_set_parent_rejects_a_three_node_cycle(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    a = _seed_task(uow, project_id=project_id, org_id=org_id)
    b = _seed_task(uow, project_id=project_id, org_id=org_id)
    c = _seed_task(uow, project_id=project_id, org_id=org_id)
    service = _make_service(uow, project_context)

    # a -> parent b -> parent c ; now try to make c's parent = a (cycle)
    await service.set_parent(task_id=a.id, actor_user_id=actor_id, parent_task_id=b.id)
    await service.set_parent(task_id=b.id, actor_user_id=actor_id, parent_task_id=c.id)

    with pytest.raises(TaskParentCycleError):
        await service.set_parent(task_id=c.id, actor_user_id=actor_id, parent_task_id=a.id)


@pytest.mark.asyncio
async def test_add_dependency_rejects_self_dependency(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    task = _seed_task(uow, project_id=project_id, org_id=org_id)
    service = _make_service(uow, project_context)

    with pytest.raises(TaskCannotDependOnItselfError):
        await service.add_dependency(task_id=task.id, actor_user_id=actor_id, depends_on_task_id=task.id)


@pytest.mark.asyncio
async def test_add_dependency_rejects_duplicate(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    a = _seed_task(uow, project_id=project_id, org_id=org_id)
    b = _seed_task(uow, project_id=project_id, org_id=org_id)
    service = _make_service(uow, project_context)

    await service.add_dependency(task_id=a.id, actor_user_id=actor_id, depends_on_task_id=b.id)
    with pytest.raises(TaskDependencyAlreadyExistsError):
        await service.add_dependency(task_id=a.id, actor_user_id=actor_id, depends_on_task_id=b.id)


@pytest.mark.asyncio
async def test_add_dependency_rejects_a_transitive_cycle(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    a = _seed_task(uow, project_id=project_id, org_id=org_id)
    b = _seed_task(uow, project_id=project_id, org_id=org_id)
    c = _seed_task(uow, project_id=project_id, org_id=org_id)
    service = _make_service(uow, project_context)

    # a depends on b, b depends on c ; adding "c depends on a" would cycle
    await service.add_dependency(task_id=a.id, actor_user_id=actor_id, depends_on_task_id=b.id)
    await service.add_dependency(task_id=b.id, actor_user_id=actor_id, depends_on_task_id=c.id)

    with pytest.raises(TaskDependencyCycleError):
        await service.add_dependency(task_id=c.id, actor_user_id=actor_id, depends_on_task_id=a.id)


@pytest.mark.asyncio
async def test_list_blocking_tasks_returns_the_dependency(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    a = _seed_task(uow, project_id=project_id, org_id=org_id)
    b = _seed_task(uow, project_id=project_id, org_id=org_id)
    service = _make_service(uow, project_context)

    await service.add_dependency(task_id=a.id, actor_user_id=actor_id, depends_on_task_id=b.id)
    blocking = await service.list_blocking_tasks(task_id=a.id)

    assert len(blocking) == 1
    assert blocking[0].id == b.id


@pytest.mark.asyncio
async def test_is_blocked_true_until_blocking_task_is_done(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    a = _seed_task(uow, project_id=project_id, org_id=org_id)
    b = _seed_task(uow, project_id=project_id, org_id=org_id)
    service = _make_service(uow, project_context)

    await service.add_dependency(task_id=a.id, actor_user_id=actor_id, depends_on_task_id=b.id)
    assert await service.is_blocked(task_id=a.id) is True

    from app.tasks.domain.workflow import DEFAULT_WORKFLOW, TaskStatus

    b.change_status(TaskStatus.TODO, workflow=DEFAULT_WORKFLOW)
    b.change_status(TaskStatus.IN_PROGRESS, workflow=DEFAULT_WORKFLOW)
    b.change_status(TaskStatus.REVIEW, workflow=DEFAULT_WORKFLOW)
    b.change_status(TaskStatus.TESTING, workflow=DEFAULT_WORKFLOW)
    b.change_status(TaskStatus.DONE, workflow=DEFAULT_WORKFLOW)

    assert await service.is_blocked(task_id=a.id) is False
