import pytest

from app.discord_integration.domain.entities import GuildLink, GuildSetupToken
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def test_guild_link_add_then_get_by_id_round_trips(uow) -> None:
    org_id, user_id = OrgId(new_uuid7()), UserId(new_uuid7())
    link = GuildLink.create(
        org_id=org_id, discord_guild_id=f"guild-{new_uuid7().hex[:8]}", discord_guild_name="Acme HQ",
        linked_by_user_id=user_id,
    )
    await uow.guild_links.add(link)
    await uow.session.flush()

    fetched = await uow.guild_links.get_by_id(link.id)

    assert fetched is not None
    assert fetched.discord_guild_id == link.discord_guild_id
    assert fetched.status.value == "active"


async def test_guild_link_update_persists_revoke_and_bumps_version(uow) -> None:
    org_id, user_id = OrgId(new_uuid7()), UserId(new_uuid7())
    link = GuildLink.create(
        org_id=org_id, discord_guild_id=f"guild-{new_uuid7().hex[:8]}", discord_guild_name="Acme HQ",
        linked_by_user_id=user_id,
    )
    await uow.guild_links.add(link)
    await uow.session.flush()

    link.revoke(revoked_by_user_id=user_id)
    await uow.guild_links.update(link)
    await uow.session.flush()

    fetched = await uow.guild_links.get_by_id(link.id)
    assert fetched.status.value == "revoked"
    assert fetched.version == 2


async def test_only_one_active_link_per_discord_guild_id(uow) -> None:
    """The partial-unique index (uq_guild_links_discord_guild_id_active) is
    the actual business rule this test guards — a second ACTIVE row for the
    same discord_guild_id must be rejected at the database level even if
    application-layer code somewhere forgot to check."""
    discord_guild_id = f"guild-{new_uuid7().hex[:8]}"
    first = GuildLink.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=discord_guild_id, discord_guild_name="Acme HQ",
        linked_by_user_id=UserId(new_uuid7()),
    )
    await uow.guild_links.add(first)
    await uow.session.flush()

    second = GuildLink.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=discord_guild_id, discord_guild_name="Impostor HQ",
        linked_by_user_id=UserId(new_uuid7()),
    )
    await uow.guild_links.add(second)
    with pytest.raises(Exception):
        await uow.session.flush()


async def test_get_active_by_discord_guild_id_ignores_revoked_rows(uow) -> None:
    discord_guild_id = f"guild-{new_uuid7().hex[:8]}"
    link = GuildLink.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=discord_guild_id, discord_guild_name="Acme HQ",
        linked_by_user_id=UserId(new_uuid7()),
    )
    await uow.guild_links.add(link)
    await uow.session.flush()

    assert await uow.guild_links.get_active_by_discord_guild_id(discord_guild_id) is not None

    link.revoke(revoked_by_user_id=UserId(new_uuid7()))
    await uow.guild_links.update(link)
    await uow.session.flush()

    assert await uow.guild_links.get_active_by_discord_guild_id(discord_guild_id) is None
    # ...but get_by_discord_guild_id (any status) still finds it, since
    # complete_setup needs the revoked row to relink().
    assert await uow.guild_links.get_by_discord_guild_id(discord_guild_id) is not None


async def test_list_for_org_returns_only_that_orgs_links(uow) -> None:
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    ours = GuildLink.create(
        org_id=org_id, discord_guild_id=f"guild-{new_uuid7().hex[:8]}", discord_guild_name="Ours",
        linked_by_user_id=UserId(new_uuid7()),
    )
    theirs = GuildLink.create(
        org_id=other_org_id, discord_guild_id=f"guild-{new_uuid7().hex[:8]}", discord_guild_name="Theirs",
        linked_by_user_id=UserId(new_uuid7()),
    )
    await uow.guild_links.add(ours)
    await uow.guild_links.add(theirs)
    await uow.session.flush()

    listed = await uow.guild_links.list_for_org(org_id)

    assert [link.id for link in listed] == [ours.id]


async def test_setup_token_add_then_get_by_token_hash_round_trips(uow) -> None:
    org_id, user_id = OrgId(new_uuid7()), UserId(new_uuid7())
    token = GuildSetupToken.create(org_id=org_id, requested_by_user_id=user_id, token_hash="a-unique-hash")
    await uow.guild_setup_tokens.add(token)
    await uow.session.flush()

    fetched = await uow.guild_setup_tokens.get_by_token_hash("a-unique-hash")

    assert fetched is not None
    assert fetched.id == token.id


async def test_invalidate_outstanding_for_org_consumes_unconsumed_tokens(uow) -> None:
    org_id, user_id = OrgId(new_uuid7()), UserId(new_uuid7())
    token = GuildSetupToken.create(org_id=org_id, requested_by_user_id=user_id, token_hash="hash-to-invalidate")
    await uow.guild_setup_tokens.add(token)
    await uow.session.flush()

    await uow.guild_setup_tokens.invalidate_outstanding_for_org(org_id)
    await uow.session.flush()

    fetched = await uow.guild_setup_tokens.get_by_token_hash("hash-to-invalidate")
    assert fetched.is_consumed()
