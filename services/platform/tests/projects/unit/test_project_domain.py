import pytest

from app.projects.domain.entities import Project, ProjectStatus, ProjectVisibility
from app.projects.domain.exceptions import InvalidProjectStatusTransitionError, ProjectAlreadyDeletedError
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7


def _new_project() -> Project:
    return Project.create(workspace_id=EntityId(new_uuid7()), org_id=OrgId(new_uuid7()), name="Demo")


def test_create_starts_in_planning() -> None:
    project = _new_project()
    assert project.status == ProjectStatus.PLANNING
    assert project.archived_at is None


def test_valid_status_transition_succeeds() -> None:
    project = _new_project()
    project.change_status(ProjectStatus.ACTIVE)
    assert project.status == ProjectStatus.ACTIVE


def test_invalid_status_transition_raises() -> None:
    project = _new_project()
    project.change_status(ProjectStatus.ACTIVE)
    project.change_status(ProjectStatus.COMPLETED)
    with pytest.raises(InvalidProjectStatusTransitionError):
        project.change_status(ProjectStatus.PLANNING)


def test_archive_sets_archived_at_and_unarchive_clears_it() -> None:
    project = _new_project()
    project.archive()
    assert project.status == ProjectStatus.ARCHIVED
    assert project.archived_at is not None

    project.unarchive()
    assert project.status == ProjectStatus.ACTIVE
    assert project.archived_at is None


def test_changing_to_the_same_status_is_a_no_op() -> None:
    project = _new_project()
    project.change_status(ProjectStatus.PLANNING)
    assert project.status == ProjectStatus.PLANNING


def test_change_visibility_updates_and_records_event() -> None:
    project = _new_project()
    project.pull_domain_events()
    project.change_visibility(ProjectVisibility.ORGANIZATION)
    assert project.visibility == ProjectVisibility.ORGANIZATION
    events = project.pull_domain_events()
    assert events[0].visibility == "organization"


def test_update_metadata_merges_rather_than_replaces() -> None:
    project = _new_project()
    project.update_metadata({"tag": "backend"})
    project.update_metadata({"priority": "high"})
    assert project.metadata == {"tag": "backend", "priority": "high"}


def test_mark_deleted_then_mark_deleted_again_raises() -> None:
    project = _new_project()
    project.mark_deleted()
    assert project.deleted_at is not None
    with pytest.raises(ProjectAlreadyDeletedError):
        project.mark_deleted()


def test_assert_not_deleted_raises_after_deletion() -> None:
    project = _new_project()
    project.mark_deleted()
    with pytest.raises(ProjectAlreadyDeletedError):
        project.assert_not_deleted()
