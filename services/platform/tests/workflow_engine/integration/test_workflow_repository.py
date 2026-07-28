import pytest

from app.workflow_engine.domain.entities import WorkflowDefinition, WorkflowState, WorkflowTransition
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def test_add_then_get_by_id_round_trips(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    workflow = WorkflowDefinition.create(project_id=project_id, org_id=org_id, name="Bug Triage")
    await uow.workflows.add(workflow)
    await uow.session.flush()

    fetched = await uow.workflows.get_by_id(workflow.id)

    assert fetched is not None
    assert fetched.name == "Bug Triage"
    assert fetched.project_id == project_id


async def test_update_persists_archive_and_bumps_version(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    workflow = WorkflowDefinition.create(project_id=project_id, org_id=org_id, name="Demo")
    await uow.workflows.add(workflow)
    await uow.session.flush()

    workflow.archive()
    await uow.workflows.update(workflow)
    await uow.session.flush()

    fetched = await uow.workflows.get_by_id(workflow.id)
    assert fetched.status.value == "archived"
    assert fetched.version == 2


async def test_list_for_project_excludes_archived_by_default(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    active = WorkflowDefinition.create(project_id=project_id, org_id=org_id, name="Active")
    archived = WorkflowDefinition.create(project_id=project_id, org_id=org_id, name="Archived")
    archived.archive()
    await uow.workflows.add(active)
    await uow.workflows.add(archived)
    await uow.session.flush()

    visible = await uow.workflows.list_for_project(project_id)
    visible_ids = {w.id for w in visible}

    assert active.id in visible_ids
    assert archived.id not in visible_ids


async def test_state_get_initial_and_transition_references_state(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    workflow = WorkflowDefinition.create(project_id=project_id, org_id=org_id, name="Demo")
    await uow.workflows.add(workflow)
    await uow.session.flush()

    todo = WorkflowState.create(workflow_id=workflow.id, name="Todo", position=1.0, is_initial=True)
    done = WorkflowState.create(workflow_id=workflow.id, name="Done", position=2.0)
    await uow.states.add(todo)
    await uow.states.add(done)
    await uow.session.flush()

    initial = await uow.states.get_initial(workflow.id)
    assert initial is not None
    assert initial.id == todo.id

    assert await uow.transitions.references_state(todo.id) is False

    transition = WorkflowTransition.create(workflow_id=workflow.id, name="Complete", from_state_id=todo.id, to_state_id=done.id, position=1.0)
    await uow.transitions.add(transition)
    await uow.session.flush()

    assert await uow.transitions.references_state(todo.id) is True
