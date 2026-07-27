import pytest

from app.projects.domain.entities import Workspace, WorkspaceStatus
from app.projects.domain.events import WorkspaceArchived, WorkspaceCreated, WorkspaceReactivated
from app.projects.domain.exceptions import WorkspaceNotActiveError
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7


def test_create_records_workspace_created_event() -> None:
    org_id = OrgId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Engineering", slug="engineering")

    assert workspace.status == WorkspaceStatus.ACTIVE
    events = workspace.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], WorkspaceCreated)
    assert events[0].org_id == org_id


def test_assert_active_passes_for_active_workspace() -> None:
    workspace = Workspace.create(org_id=OrgId(new_uuid7()), name="Engineering", slug="engineering")
    workspace.assert_active()  # should not raise


def test_assert_active_raises_once_archived() -> None:
    workspace = Workspace.create(org_id=OrgId(new_uuid7()), name="Engineering", slug="engineering")
    workspace.archive()
    with pytest.raises(WorkspaceNotActiveError):
        workspace.assert_active()


def test_archive_then_reactivate_round_trips() -> None:
    workspace = Workspace.create(org_id=OrgId(new_uuid7()), name="Engineering", slug="engineering")
    workspace.pull_domain_events()

    workspace.archive()
    assert workspace.status == WorkspaceStatus.ARCHIVED
    archived_events = workspace.pull_domain_events()
    assert isinstance(archived_events[0], WorkspaceArchived)

    workspace.reactivate()
    assert workspace.status == WorkspaceStatus.ACTIVE
    reactivated_events = workspace.pull_domain_events()
    assert isinstance(reactivated_events[0], WorkspaceReactivated)


def test_update_settings_merges() -> None:
    workspace = Workspace.create(org_id=OrgId(new_uuid7()), name="Engineering", slug="engineering")
    workspace.update_settings({"default_view": "board"})
    workspace.update_settings({"color": "blue"})
    assert workspace.settings == {"default_view": "board", "color": "blue"}
