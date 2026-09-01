from datetime import timedelta

from app.discord_integration.domain.entities import GuildLink, GuildLinkStatus, GuildSetupToken
from app.discord_integration.domain.events import GuildLinked, GuildRelinked, GuildUnlinked
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


def _org() -> OrgId:
    return OrgId(new_uuid7())


def _user() -> UserId:
    return UserId(new_uuid7())


def test_create_records_guild_linked_event() -> None:
    org_id, user_id = _org(), _user()
    link = GuildLink.create(org_id=org_id, discord_guild_id="123", discord_guild_name="Acme HQ", linked_by_user_id=user_id)

    assert link.status == GuildLinkStatus.ACTIVE
    assert link.is_active()
    events = link.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], GuildLinked)
    assert events[0].discord_guild_id == "123"


def test_revoke_transitions_status_and_records_event() -> None:
    link = GuildLink.create(org_id=_org(), discord_guild_id="123", discord_guild_name="Acme HQ", linked_by_user_id=_user())
    link.pull_domain_events()
    revoker = _user()

    link.revoke(revoked_by_user_id=revoker)

    assert link.status == GuildLinkStatus.REVOKED
    assert not link.is_active()
    assert link.revoked_by_user_id == revoker
    assert link.revoked_at is not None
    events = link.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], GuildUnlinked)


def test_revoke_accepts_no_actor_for_bot_initiated_unlink() -> None:
    link = GuildLink.create(org_id=_org(), discord_guild_id="123", discord_guild_name="Acme HQ", linked_by_user_id=_user())
    link.revoke(revoked_by_user_id=None)
    assert link.revoked_by_user_id is None


def test_relink_reclaims_a_revoked_link_for_a_new_org() -> None:
    original_org = _org()
    link = GuildLink.create(org_id=original_org, discord_guild_id="123", discord_guild_name="Old Name", linked_by_user_id=_user())
    link.revoke(revoked_by_user_id=_user())
    link.pull_domain_events()

    new_org = _org()
    new_linker = _user()
    link.relink(org_id=new_org, discord_guild_name="New Name", linked_by_user_id=new_linker)

    assert link.org_id == new_org
    assert link.discord_guild_name == "New Name"
    assert link.status == GuildLinkStatus.ACTIVE
    assert link.linked_by_user_id == new_linker
    assert link.revoked_at is None
    assert link.revoked_by_user_id is None
    events = link.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], GuildRelinked)


def test_setup_token_create_defaults_to_a_fifteen_minute_expiry() -> None:
    token = GuildSetupToken.create(org_id=_org(), requested_by_user_id=_user(), token_hash="hashed")
    assert token.expires_at - token.created_at == timedelta(minutes=15)
    assert not token.is_expired()
    assert not token.is_consumed()


def test_setup_token_is_expired_reflects_ttl() -> None:
    token = GuildSetupToken.create(org_id=_org(), requested_by_user_id=_user(), token_hash="hashed", ttl=timedelta(seconds=-1))
    assert token.is_expired()


def test_setup_token_consume_records_the_claiming_guild() -> None:
    token = GuildSetupToken.create(org_id=_org(), requested_by_user_id=_user(), token_hash="hashed")
    token.consume(discord_guild_id="999")
    assert token.is_consumed()
    assert token.consumed_by_discord_guild_id == "999"
