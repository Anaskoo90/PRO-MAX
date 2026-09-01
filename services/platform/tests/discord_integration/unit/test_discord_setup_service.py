from datetime import timedelta

import pytest

from app.discord_integration.application.discord_setup import DiscordSetupService
from app.discord_integration.domain.exceptions import (
    GuildAlreadyLinkedToAnotherOrganizationError,
    GuildLinkNotFoundError,
    GuildNotLinkedError,
    InsufficientDiscordPermissionError,
    InvalidSetupCodeError,
    SetupCodeAlreadyUsedError,
    SetupCodeExpiredError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow
from tests.discord_integration.unit.fakes import (
    AllowAllPermissionChecker,
    DenyAllPermissionChecker,
    FakeDiscordIntegrationUnitOfWork,
    FakeOrganizationLookup,
)

pytestmark = pytest.mark.asyncio


def _make_service(uow, permission_checker=None, organization_lookup=None) -> DiscordSetupService:
    return DiscordSetupService(
        uow_factory=lambda: uow,
        dispatcher=EventDispatcher(),
        permission_checker=permission_checker or AllowAllPermissionChecker(),
        organization_lookup=organization_lookup or FakeOrganizationLookup(),
        discord_application_id="123456",
    )


@pytest.fixture
def context():
    return FakeDiscordIntegrationUnitOfWork(), OrgId(new_uuid7()), UserId(new_uuid7())


async def test_request_setup_token_succeeds_for_a_permitted_user(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)

    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)

    assert len(token.raw_code) == 8
    assert "123456" in token.invite_url
    assert token.expires_at > utcnow()


async def test_request_setup_token_rejects_a_user_without_permission(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientDiscordPermissionError):
        await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)


async def test_request_setup_token_supersedes_an_outstanding_token(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)

    await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)

    assert len(uow.guild_setup_tokens.tokens) == 2
    unconsumed = [t for t in uow.guild_setup_tokens.tokens.values() if t.consumed_at is None]
    assert len(unconsumed) == 1  # the first was superseded (consumed) by the second request


async def test_complete_setup_creates_a_new_guild_link(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)

    link = await service.complete_setup(
        raw_code=token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    assert link.org_id == org_id
    assert link.discord_guild_id == "111"
    assert link.status == "active"


async def test_complete_setup_rejects_an_unknown_code(context) -> None:
    uow, _org_id, _actor_id = context
    service = _make_service(uow)

    with pytest.raises(InvalidSetupCodeError):
        await service.complete_setup(
            raw_code="does-not-exist", discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
        )


async def test_complete_setup_rejects_an_already_used_code(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    await service.complete_setup(
        raw_code=token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    with pytest.raises(SetupCodeAlreadyUsedError):
        await service.complete_setup(
            raw_code=token.raw_code, discord_guild_id="222", discord_guild_name="Other", discord_user_id="999",
        )


async def test_complete_setup_rejects_an_expired_code(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    stored_token = next(iter(uow.guild_setup_tokens.tokens.values()))
    stored_token.expires_at = utcnow() - timedelta(seconds=1)

    with pytest.raises(SetupCodeExpiredError):
        await service.complete_setup(
            raw_code=token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
        )


async def test_complete_setup_rejects_a_guild_already_linked_to_another_org(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    first_token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    await service.complete_setup(
        raw_code=first_token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    other_org_id = OrgId(new_uuid7())
    second_token = await service.request_setup_token(org_id=other_org_id, requested_by_user_id=UserId(new_uuid7()))

    with pytest.raises(GuildAlreadyLinkedToAnotherOrganizationError):
        await service.complete_setup(
            raw_code=second_token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ Take 2",
            discord_user_id="999",
        )


async def test_complete_setup_relinks_a_previously_revoked_guild_to_a_new_org(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    first_token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    first_link = await service.complete_setup(
        raw_code=first_token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )
    await service.unlink_guild(org_id=org_id, guild_link_id=first_link.id, actor_user_id=actor_id)

    new_org_id = OrgId(new_uuid7())
    new_actor_id = UserId(new_uuid7())
    second_token = await service.request_setup_token(org_id=new_org_id, requested_by_user_id=new_actor_id)

    relinked = await service.complete_setup(
        raw_code=second_token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ Renamed",
        discord_user_id="999",
    )

    assert relinked.id == first_link.id  # same row reclaimed, not a new one
    assert relinked.org_id == new_org_id
    assert relinked.status == "active"


async def test_list_guild_links_returns_only_the_orgs_own_links(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    await service.complete_setup(
        raw_code=token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    other_org_id = OrgId(new_uuid7())
    other_token = await service.request_setup_token(org_id=other_org_id, requested_by_user_id=UserId(new_uuid7()))
    await service.complete_setup(
        raw_code=other_token.raw_code, discord_guild_id="222", discord_guild_name="Other Org", discord_user_id="999",
    )

    links = await service.list_guild_links(org_id=org_id, actor_user_id=actor_id)

    assert len(links) == 1
    assert links[0].discord_guild_id == "111"


async def test_list_guild_links_rejects_a_user_without_permission(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientDiscordPermissionError):
        await service.list_guild_links(org_id=org_id, actor_user_id=actor_id)


async def test_unlink_guild_rejects_a_link_belonging_to_another_org(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    link = await service.complete_setup(
        raw_code=token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    wrong_org_id = OrgId(new_uuid7())
    with pytest.raises(GuildLinkNotFoundError):
        await service.unlink_guild(org_id=wrong_org_id, guild_link_id=link.id, actor_user_id=actor_id)


async def test_unlink_guild_by_discord_id_requires_no_guilddesk_permission(context) -> None:
    """Bot-initiated path: authorization is Discord's own 'Manage Server'
    gate plus the bot service secret (see bot_authentication.py), not
    GuildDesk RBAC — this must succeed even against a DenyAllPermissionChecker."""
    uow, org_id, actor_id = context
    service = _make_service(uow, permission_checker=DenyAllPermissionChecker())
    # Seed a link via a *separate* permissive service instance sharing the
    # same uow — this test is specifically about the unlink call itself
    # not checking GuildDesk permissions, so setup must go through a path
    # that isn't gated by the DenyAllPermissionChecker under test.
    permissive_service = _make_service(uow, permission_checker=AllowAllPermissionChecker())
    setup_token = await permissive_service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    await permissive_service.complete_setup(
        raw_code=setup_token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    await service.unlink_guild_by_discord_id(discord_guild_id="111", discord_user_id="999")

    link = await uow.guild_links.get_by_discord_guild_id("111")
    assert link.status == "revoked"
    assert link.revoked_by_user_id is None


async def test_unlink_guild_by_discord_id_raises_when_not_linked(context) -> None:
    uow, _org_id, _actor_id = context
    service = _make_service(uow)

    with pytest.raises(GuildNotLinkedError):
        await service.unlink_guild_by_discord_id(discord_guild_id="does-not-exist", discord_user_id="999")


async def test_get_status_reports_unlinked_for_an_unknown_guild(context) -> None:
    uow, _org_id, _actor_id = context
    service = _make_service(uow)

    status = await service.get_status_by_discord_guild_id(discord_guild_id="does-not-exist")

    assert status.linked is False
    assert status.org_name is None


async def test_get_status_reports_linked_with_org_name(context) -> None:
    uow, org_id, actor_id = context
    lookup = FakeOrganizationLookup(names={org_id: "Acme Corp"})
    service = _make_service(uow, organization_lookup=lookup)
    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    await service.complete_setup(
        raw_code=token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    status = await service.get_status_by_discord_guild_id(discord_guild_id="111")

    assert status.linked is True
    assert status.org_name == "Acme Corp"
    assert status.discord_guild_name == "Acme HQ"


async def test_resolve_org_id_returns_none_for_an_unknown_guild(context) -> None:
    uow, _org_id, _actor_id = context
    service = _make_service(uow)

    assert await service.resolve_org_id_by_discord_guild_id(discord_guild_id="does-not-exist") is None


async def test_resolve_org_id_returns_the_linked_org(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    await service.complete_setup(
        raw_code=token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    resolved = await service.resolve_org_id_by_discord_guild_id(discord_guild_id="111")

    assert resolved == org_id


async def test_resolve_org_id_returns_none_for_a_revoked_link(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    token = await service.request_setup_token(org_id=org_id, requested_by_user_id=actor_id)
    link = await service.complete_setup(
        raw_code=token.raw_code, discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )
    await service.unlink_guild(org_id=org_id, guild_link_id=link.id, actor_user_id=actor_id)

    assert await service.resolve_org_id_by_discord_guild_id(discord_guild_id="111") is None
