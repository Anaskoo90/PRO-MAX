import pytest

from app.tasks.application.ports import ProjectMemberSummary, ProjectSummary
from app.tasks.application.task_ordering import AutoOrderStrategy, TaskOrderingService
from app.tasks.domain.entities import Task
from app.tasks.domain.workflow import TaskPriority
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.tasks.unit.fakes import AllowAllPermissionChecker, FakeProjectContext, FakeTasksUnitOfWork


def _make_service(uow, project_context) -> TaskOrderingService:
    return TaskOrderingService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker(),
        project_context=project_context,
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
async def test_move_task_between_two_neighbors(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    first = Task.create(project_id=project_id, org_id=org_id, title="First", position=100.0)
    second = Task.create(project_id=project_id, org_id=org_id, title="Second", position=200.0)
    moved = Task.create(project_id=project_id, org_id=org_id, title="Moved", position=300.0)
    for t in (first, second, moved):
        uow.tasks.tasks[t.id] = t

    service = _make_service(uow, project_context)
    result = await service.move_task(task_id=moved.id, actor_user_id=actor_id, previous_task_id=first.id, next_task_id=second.id)

    assert first.position < result.position < second.position


@pytest.mark.asyncio
async def test_move_task_to_the_start_of_the_list(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    first = Task.create(project_id=project_id, org_id=org_id, title="First", position=100.0)
    moved = Task.create(project_id=project_id, org_id=org_id, title="Moved", position=300.0)
    uow.tasks.tasks[first.id] = first
    uow.tasks.tasks[moved.id] = moved

    service = _make_service(uow, project_context)
    result = await service.move_task(task_id=moved.id, actor_user_id=actor_id, previous_task_id=None, next_task_id=first.id)

    assert result.position < first.position


@pytest.mark.asyncio
async def test_auto_order_by_priority_does_not_change_stored_position(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    low = Task.create(project_id=project_id, org_id=org_id, title="Low", priority=TaskPriority.LOW, position=1.0)
    critical = Task.create(project_id=project_id, org_id=org_id, title="Critical", priority=TaskPriority.CRITICAL, position=2.0)
    uow.tasks.tasks[low.id] = low
    uow.tasks.tasks[critical.id] = critical

    service = _make_service(uow, project_context)
    ordered = await service.list_auto_ordered(project_id=project_id, strategy=AutoOrderStrategy.PRIORITY_DESC)

    assert ordered[0].id == critical.id
    assert ordered[1].id == low.id
    # stored positions untouched
    assert low.position == 1.0
    assert critical.position == 2.0
