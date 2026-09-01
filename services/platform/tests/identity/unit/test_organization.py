import pytest

from app.identity.domain.exceptions import InvalidOrganizationSlugError
from app.identity.domain.organization import Organization, OrganizationStatus
from app.identity.domain.events import OrganizationCreated
from app.platform_core.shared_kernel.types import UserId
from app.platform_core.shared_kernel.utils import new_uuid7


def _owner_id() -> UserId:
    return UserId(new_uuid7())


def test_create_records_organization_created_event() -> None:
    owner = _owner_id()
    org = Organization.create(name="Acme", slug="acme", owner_user_id=owner)

    assert org.status == OrganizationStatus.ACTIVE
    assert org.owner_user_id == owner
    events = org.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], OrganizationCreated)
    assert events[0].slug == "acme"


@pytest.mark.parametrize("bad_slug", ["", "-leading-dash", "UPPERCASE", "has space", "trailing-dash-"])
def test_create_rejects_invalid_slug(bad_slug: str) -> None:
    with pytest.raises(InvalidOrganizationSlugError):
        Organization.create(name="Acme", slug=bad_slug, owner_user_id=_owner_id())


def test_update_settings_merges_rather_than_replaces() -> None:
    org = Organization.create(name="Acme", slug="acme", owner_user_id=_owner_id())
    org.update_settings({"ip_allowlist": ["10.0.0.0/8"]})
    org.update_settings({"feature_x_enabled": True})

    assert org.settings["ip_allowlist"] == ["10.0.0.0/8"]
    assert org.settings["feature_x_enabled"] is True


def test_transfer_ownership_updates_owner_and_records_event() -> None:
    org = Organization.create(name="Acme", slug="acme", owner_user_id=_owner_id())
    org.pull_domain_events()
    new_owner = _owner_id()

    org.transfer_ownership(new_owner)

    assert org.owner_user_id == new_owner
    events = org.pull_domain_events()
    assert events[0].new_owner_user_id == new_owner


def test_suspend_then_reactivate_round_trips_status() -> None:
    org = Organization.create(name="Acme", slug="acme", owner_user_id=_owner_id())

    org.suspend()
    assert org.status == OrganizationStatus.SUSPENDED
    assert not org.is_active()

    org.reactivate()
    assert org.status == OrganizationStatus.ACTIVE
    assert org.is_active()


def test_ip_allowlist_and_denylist_read_from_settings() -> None:
    org = Organization.create(name="Acme", slug="acme", owner_user_id=_owner_id())
    org.update_settings({"ip_allowlist": ["10.0.0.0/8"], "ip_denylist": ["1.2.3.4/32"]})

    assert org.ip_allowlist() == ["10.0.0.0/8"]
    assert org.ip_denylist() == ["1.2.3.4/32"]


def test_change_slug_updates_the_slug() -> None:
    org = Organization.create(name="Acme", slug="acme", owner_user_id=_owner_id())

    org.change_slug("acme-corp")

    assert org.slug == "acme-corp"


@pytest.mark.parametrize("bad_slug", ["", "-leading-dash", "UPPERCASE", "has space"])
def test_change_slug_rejects_an_invalid_slug(bad_slug: str) -> None:
    org = Organization.create(name="Acme", slug="acme", owner_user_id=_owner_id())

    with pytest.raises(InvalidOrganizationSlugError):
        org.change_slug(bad_slug)


def test_update_description_sets_the_description() -> None:
    org = Organization.create(name="Acme", slug="acme", owner_user_id=_owner_id())
    assert org.description is None

    org.update_description("A widget company")

    assert org.description == "A widget company"


def test_update_logo_url_sets_and_clears_the_logo() -> None:
    org = Organization.create(name="Acme", slug="acme", owner_user_id=_owner_id())

    org.update_logo_url("https://cdn.example.com/logo.png")
    assert org.logo_url == "https://cdn.example.com/logo.png"

    org.update_logo_url(None)
    assert org.logo_url is None
