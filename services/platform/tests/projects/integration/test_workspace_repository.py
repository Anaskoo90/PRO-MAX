import pytest

from app.projects.domain.entities import Workspace
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def test_add_then_get_by_id_round_trips(uow) -> None:
    org_id = OrgId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Engineering", slug=f"eng-{new_uuid7().hex[:8]}")
    await uow.workspaces.add(workspace)
    await uow.session.flush()

    fetched = await uow.workspaces.get_by_id(workspace.id)

    assert fetched is not None
    assert fetched.slug == workspace.slug
    assert fetched.org_id == org_id


async def test_get_by_slug_finds_the_workspace(uow) -> None:
    org_id = OrgId(new_uuid7())
    slug = f"eng-{new_uuid7().hex[:8]}"
    workspace = Workspace.create(org_id=org_id, name="Engineering", slug=slug)
    await uow.workspaces.add(workspace)
    await uow.session.flush()

    fetched = await uow.workspaces.get_by_slug(org_id, slug)

    assert fetched is not None
    assert fetched.id == workspace.id


async def test_update_persists_settings_and_bumps_version(uow) -> None:
    org_id = OrgId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Engineering", slug=f"eng-{new_uuid7().hex[:8]}")
    await uow.workspaces.add(workspace)
    await uow.session.flush()

    workspace.update_settings({"default_view": "board"})
    await uow.workspaces.update(workspace)
    await uow.session.flush()

    fetched = await uow.workspaces.get_by_id(workspace.id)
    assert fetched.settings["default_view"] == "board"
    assert fetched.version == 2
