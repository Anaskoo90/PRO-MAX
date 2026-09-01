from app.ticket_system.domain.entities import TicketCategory
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7


def test_create_builds_an_active_category_with_the_given_fields() -> None:
    org_id = OrgId(new_uuid7())

    category = TicketCategory.create(
        org_id=org_id, discord_guild_id="111", name="Billing", discord_category_channel_id="222",
        staff_discord_role_ids=["role-1", "role-2"],
    )

    assert category.org_id == org_id
    assert category.discord_guild_id == "111"
    assert category.name == "Billing"
    assert category.discord_category_channel_id == "222"
    assert category.staff_discord_role_ids == ["role-1", "role-2"]
    assert category.is_active is True
    assert category.version == 1


def test_create_defaults_to_no_staff_roles() -> None:
    category = TicketCategory.create(
        org_id=OrgId(new_uuid7()), discord_guild_id="111", name="General", discord_category_channel_id="222",
        staff_discord_role_ids=[],
    )
    assert category.staff_discord_role_ids == []
