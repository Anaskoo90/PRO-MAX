import pytest

from app.ticket_system.application.ticket_categories import TicketCategoryService
from app.ticket_system.domain.exceptions import (
    GuildNotLinkedForTicketsError,
    InsufficientTicketPermissionError,
    TicketCategoryNotFoundError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.ticket_system.unit.fakes import (
    AllowAllPermissionChecker,
    DenyAllPermissionChecker,
    FakeGuildResolver,
    FakeTicketUnitOfWork,
)

pytestmark = pytest.mark.asyncio


def _make_service(uow, permission_checker=None, guild_resolver=None) -> TicketCategoryService:
    return TicketCategoryService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(),
        permission_checker=permission_checker or AllowAllPermissionChecker(),
        guild_resolver=guild_resolver or FakeGuildResolver(),
    )


@pytest.fixture
def context():
    return FakeTicketUnitOfWork(), OrgId(new_uuid7()), UserId(new_uuid7())


async def test_create_category_succeeds_for_a_permitted_user(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)

    category = await service.create_category(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", name="Billing",
        discord_category_channel_id="222", staff_discord_role_ids=["role-1"],
    )

    assert category.name == "Billing"
    assert category.staff_discord_role_ids == ["role-1"]
    assert category.is_active is True
    assert any(r.action == "ticket_category_created" for r in uow.audit_logs.records)


async def test_create_category_rejects_a_user_without_permission(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientTicketPermissionError):
        await service.create_category(
            org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", name="Billing",
            discord_category_channel_id="222", staff_discord_role_ids=[],
        )


async def test_list_for_guild_returns_only_that_guilds_categories(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    await service.create_category(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", name="Ours",
        discord_category_channel_id="222", staff_discord_role_ids=[],
    )
    await service.create_category(
        org_id=OrgId(new_uuid7()), actor_user_id=UserId(new_uuid7()), discord_guild_id="444", name="Theirs",
        discord_category_channel_id="555", staff_discord_role_ids=[],
    )

    categories = await service.list_for_guild(org_id=org_id, discord_guild_id="111")

    assert len(categories) == 1
    assert categories[0].name == "Ours"


async def test_list_for_guild_excludes_a_stale_category_from_a_different_org_sharing_the_guild_id(context) -> None:
    """Regression test for the Critical cross-org leak found in review: a
    Discord guild can be unlinked and relinked to a *different* org
    (Discord Integration's relink()), which would otherwise leave a
    different org's stale category visible under the same
    discord_guild_id. Same org_id check TicketLifecycleService already
    applies everywhere."""
    uow, org_id, actor_id = context
    service = _make_service(uow)
    await service.create_category(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", name="Ours",
        discord_category_channel_id="222", staff_discord_role_ids=[],
    )
    other_org_id = OrgId(new_uuid7())
    await service.create_category(
        org_id=other_org_id, actor_user_id=UserId(new_uuid7()), discord_guild_id="111", name="StaleFromOtherOrg",
        discord_category_channel_id="333", staff_discord_role_ids=[],
    )

    categories = await service.list_for_guild(org_id=org_id, discord_guild_id="111")

    assert [c.name for c in categories] == ["Ours"]


async def test_get_raises_not_found_for_an_unknown_category(context) -> None:
    uow, org_id, _actor_id = context
    service = _make_service(uow)

    with pytest.raises(TicketCategoryNotFoundError):
        await service.get(org_id=org_id, category_id=new_uuid7())


async def test_get_returns_the_created_category(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    created = await service.create_category(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", name="Billing",
        discord_category_channel_id="222", staff_discord_role_ids=[],
    )

    fetched = await service.get(org_id=org_id, category_id=created.id)

    assert fetched.id == created.id
    assert fetched.name == "Billing"


async def test_get_rejects_a_category_belonging_to_another_org(context) -> None:
    """The other half of the same Critical regression: fetching by id must
    not leak a category across organizations even when the id itself is
    known/guessed correctly."""
    uow, org_id, actor_id = context
    service = _make_service(uow)
    created = await service.create_category(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", name="Billing",
        discord_category_channel_id="222", staff_discord_role_ids=[],
    )

    other_org_id = OrgId(new_uuid7())
    with pytest.raises(TicketCategoryNotFoundError):
        await service.get(org_id=other_org_id, category_id=created.id)


async def test_list_for_guild_from_bot_resolves_org_and_filters(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow, guild_resolver=FakeGuildResolver(org_ids_by_guild={"111": org_id}))
    await service.create_category(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", name="Ours",
        discord_category_channel_id="222", staff_discord_role_ids=[],
    )
    await service.create_category(
        org_id=OrgId(new_uuid7()), actor_user_id=UserId(new_uuid7()), discord_guild_id="111", name="StaleFromOtherOrg",
        discord_category_channel_id="333", staff_discord_role_ids=[],
    )

    categories = await service.list_for_guild_from_bot(discord_guild_id="111")

    assert [c.name for c in categories] == ["Ours"]


async def test_list_for_guild_from_bot_rejects_an_unlinked_guild(context) -> None:
    uow, _org_id, _actor_id = context
    service = _make_service(uow, guild_resolver=FakeGuildResolver())

    with pytest.raises(GuildNotLinkedForTicketsError):
        await service.list_for_guild_from_bot(discord_guild_id="does-not-exist")


async def test_create_category_from_bot_resolves_org_via_guild_resolver(context) -> None:
    uow, org_id, _actor_id = context
    service = _make_service(uow, guild_resolver=FakeGuildResolver(org_ids_by_guild={"111": org_id}))

    category = await service.create_category_from_bot(
        discord_guild_id="111", name="Billing", discord_category_channel_id="222", staff_discord_role_ids=["role-1"],
    )

    assert category.org_id == org_id
    assert category.name == "Billing"


async def test_create_category_from_bot_rejects_an_unlinked_guild(context) -> None:
    uow, _org_id, _actor_id = context
    service = _make_service(uow, guild_resolver=FakeGuildResolver())

    with pytest.raises(GuildNotLinkedForTicketsError):
        await service.create_category_from_bot(
            discord_guild_id="does-not-exist", name="Billing", discord_category_channel_id="222",
            staff_discord_role_ids=[],
        )


async def test_create_category_from_bot_requires_no_guilddesk_permission(context) -> None:
    uow, org_id, _actor_id = context
    service = _make_service(
        uow, permission_checker=DenyAllPermissionChecker(),
        guild_resolver=FakeGuildResolver(org_ids_by_guild={"111": org_id}),
    )

    category = await service.create_category_from_bot(
        discord_guild_id="111", name="Billing", discord_category_channel_id="222", staff_discord_role_ids=[],
    )

    assert category.name == "Billing"
