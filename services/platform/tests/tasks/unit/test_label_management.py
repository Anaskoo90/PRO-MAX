import pytest

from app.tasks.application.label_management import LabelService
from app.tasks.application.ports import ProjectMemberSummary, ProjectSummary
from app.tasks.domain.entities import Task
from app.tasks.domain.exceptions import (
    InvalidLabelColorError,
    LabelAlreadyExistsError,
    TaskLabelAlreadyAttachedError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.tasks.unit.fakes import AllowAllPermissionChecker, FakeProjectContext, FakeTasksUnitOfWork


def _make_service(uow, project_context) -> LabelService:
    return LabelService(
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
async def test_create_label_with_valid_color(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)

    label = await service.create_label(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Bug", color="#FF0000")
    assert label.name == "Bug"
    assert label.color == "#FF0000"


@pytest.mark.asyncio
async def test_create_label_with_invalid_color_raises(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)

    with pytest.raises(InvalidLabelColorError):
        await service.create_label(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Bug", color="red")


@pytest.mark.asyncio
async def test_duplicate_label_name_raises(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)

    await service.create_label(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Bug", color="#FF0000")
    with pytest.raises(LabelAlreadyExistsError):
        await service.create_label(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Bug", color="#00FF00")


@pytest.mark.asyncio
async def test_attach_and_detach_label_from_task(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    task = Task.create(project_id=project_id, org_id=org_id, title="Demo")
    uow.tasks.tasks[task.id] = task
    service = _make_service(uow, project_context)
    label = await service.create_label(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Bug", color="#FF0000")

    await service.attach_label(task_id=task.id, label_id=label.id, actor_user_id=actor_id)
    labels = await service.list_labels_for_task(task_id=task.id)
    assert len(labels) == 1
    assert labels[0].id == label.id

    with pytest.raises(TaskLabelAlreadyAttachedError):
        await service.attach_label(task_id=task.id, label_id=label.id, actor_user_id=actor_id)

    await service.detach_label(task_id=task.id, label_id=label.id, actor_user_id=actor_id)
    labels_after = await service.list_labels_for_task(task_id=task.id)
    assert labels_after == []
