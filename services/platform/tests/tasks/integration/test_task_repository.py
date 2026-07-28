import pytest

from app.tasks.domain.entities import Task
from app.tasks.domain.workflow import DEFAULT_WORKFLOW, TaskStatus
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def test_add_then_get_by_id_round_trips(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    task = Task.create(project_id=project_id, org_id=org_id, title="Demo Task")
    await uow.tasks.add(task)
    await uow.session.flush()

    fetched = await uow.tasks.get_by_id(task.id)

    assert fetched is not None
    assert fetched.title == "Demo Task"
    assert fetched.project_id == project_id


async def test_update_persists_status_change_and_bumps_version(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    task = Task.create(project_id=project_id, org_id=org_id, title="Demo Task")
    await uow.tasks.add(task)
    await uow.session.flush()

    task.change_status(TaskStatus.TODO, workflow=DEFAULT_WORKFLOW)
    await uow.tasks.update(task)
    await uow.session.flush()

    fetched = await uow.tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.TODO
    assert fetched.version == 2


async def test_list_for_project_excludes_archived_by_default(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    active_task = Task.create(project_id=project_id, org_id=org_id, title="Active")
    archived_task = Task.create(project_id=project_id, org_id=org_id, title="Archived")
    archived_task.archive()
    await uow.tasks.add(active_task)
    await uow.tasks.add(archived_task)
    await uow.session.flush()

    visible = await uow.tasks.list_for_project(project_id)
    visible_ids = {t.id for t in visible}

    assert active_task.id in visible_ids
    assert archived_task.id not in visible_ids
