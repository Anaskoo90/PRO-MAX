from app.projects.domain.entities import ProjectTemplate, ProjectVisibility
from app.projects.domain.events import ProjectTemplateCreated, ProjectTemplateImported
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7


def test_create_records_only_the_created_event() -> None:
    template = ProjectTemplate.create(org_id=OrgId(new_uuid7()), name="Standard", default_metadata={"k": "v"})
    events = template.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], ProjectTemplateCreated)


def test_export_then_import_round_trips_content() -> None:
    original = ProjectTemplate.create(
        org_id=OrgId(new_uuid7()), name="Standard", description="A standard project template",
        default_visibility=ProjectVisibility.ORGANIZATION, default_metadata={"tag": "eng"},
        default_settings={"kanban": True},
    )
    exported = original.to_export_dict()

    new_org_id = OrgId(new_uuid7())
    imported = ProjectTemplate.from_import_dict(org_id=new_org_id, data=exported)

    assert imported.org_id == new_org_id
    assert imported.name == original.name
    assert imported.description == original.description
    assert imported.default_visibility == ProjectVisibility.ORGANIZATION
    assert imported.default_metadata == {"tag": "eng"}
    assert imported.default_settings == {"kanban": True}
    assert imported.is_default is False


def test_import_records_only_the_imported_event_not_created() -> None:
    original = ProjectTemplate.create(org_id=OrgId(new_uuid7()), name="Standard")
    exported = original.to_export_dict()

    imported = ProjectTemplate.from_import_dict(org_id=OrgId(new_uuid7()), data=exported)
    events = imported.pull_domain_events()

    assert len(events) == 1
    assert isinstance(events[0], ProjectTemplateImported)


def test_export_excludes_identity_fields() -> None:
    template = ProjectTemplate.create(org_id=OrgId(new_uuid7()), name="Standard")
    exported = template.to_export_dict()

    assert "id" not in exported
    assert "org_id" not in exported
    assert "version" not in exported


def test_mark_default_and_unmark_default() -> None:
    template = ProjectTemplate.create(org_id=OrgId(new_uuid7()), name="Standard")
    assert template.is_default is False

    template.mark_default()
    assert template.is_default is True

    template.unmark_default()
    assert template.is_default is False
