import pytest

from app.ticket_system.domain.entities import Ticket, TicketStatus
from app.ticket_system.domain.events import (
    TicketClaimed,
    TicketClosed,
    TicketOpened,
    TicketTransferred,
    TicketUnclaimed,
)
from app.ticket_system.domain.exceptions import InvalidTicketTransitionError
from app.ticket_system.domain.value_objects import TicketActor
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


def _org() -> OrgId:
    return OrgId(new_uuid7())


def _ticket(**overrides) -> Ticket:
    defaults = dict(
        org_id=_org(), discord_guild_id="111", ticket_number=1, discord_channel_id="222", title="Help me",
        opener=TicketActor(discord_user_id="333"),
    )
    defaults.update(overrides)
    return Ticket.create(**defaults)


def test_create_records_ticket_opened_event_and_starts_open() -> None:
    org_id = _org()
    ticket = _ticket(org_id=org_id, ticket_number=42)

    assert ticket.status == TicketStatus.OPEN
    assert ticket.is_open()
    events = ticket.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], TicketOpened)
    assert events[0].org_id == org_id
    assert events[0].ticket_number == 42


def test_ticket_actor_requires_at_least_one_identity() -> None:
    """Ticket.create() has no separate "missing opener" check of its own —
    TicketActor's own __post_init__ is the single place this invariant is
    enforced, so this is the only test needed to cover it."""
    with pytest.raises(ValueError):
        TicketActor()


def test_create_accepts_a_guilddesk_user_opener_without_a_discord_id() -> None:
    ticket = _ticket(opener=TicketActor(user_id=UserId(new_uuid7())))
    assert ticket.opener_discord_user_id is None
    assert ticket.opener_user_id is not None


def test_create_sets_created_at_automatically() -> None:
    ticket = _ticket()
    assert ticket.created_at is not None


def test_close_transitions_status_and_records_event() -> None:
    ticket = _ticket()
    ticket.pull_domain_events()
    closer = TicketActor(discord_user_id="999")

    ticket.close(actor=closer)

    assert ticket.status == TicketStatus.CLOSED
    assert not ticket.is_open()
    assert ticket.closed_at is not None
    assert ticket.closed_by_discord_user_id == "999"
    events = ticket.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], TicketClosed)


def test_close_rejects_an_already_closed_ticket() -> None:
    ticket = _ticket()
    ticket.close(actor=TicketActor(discord_user_id="999"))

    with pytest.raises(InvalidTicketTransitionError):
        ticket.close(actor=TicketActor(discord_user_id="999"))


def test_claim_transitions_status_and_records_event() -> None:
    ticket = _ticket()
    ticket.pull_domain_events()
    claimant = TicketActor(discord_user_id="777")

    ticket.claim(claimant=claimant)

    assert ticket.status == TicketStatus.CLAIMED
    assert ticket.is_claimed()
    assert not ticket.is_open()
    assert ticket.claimed_by_discord_user_id == "777"
    events = ticket.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], TicketClaimed)
    assert events[0].claimed_by_discord_user_id == "777"


def test_claim_rejects_an_already_claimed_ticket() -> None:
    ticket = _ticket()
    ticket.claim(claimant=TicketActor(discord_user_id="777"))

    with pytest.raises(InvalidTicketTransitionError):
        ticket.claim(claimant=TicketActor(discord_user_id="888"))


def test_claim_rejects_a_closed_ticket() -> None:
    ticket = _ticket()
    ticket.close(actor=TicketActor(discord_user_id="999"))

    with pytest.raises(InvalidTicketTransitionError):
        ticket.claim(claimant=TicketActor(discord_user_id="777"))


def test_unclaim_transitions_back_to_open_and_records_event() -> None:
    ticket = _ticket()
    ticket.claim(claimant=TicketActor(discord_user_id="777"))
    ticket.pull_domain_events()

    ticket.unclaim()

    assert ticket.status == TicketStatus.OPEN
    assert ticket.is_open()
    assert ticket.claimed_by_discord_user_id is None
    assert ticket.claimed_by_user_id is None
    events = ticket.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], TicketUnclaimed)


def test_unclaim_rejects_an_unclaimed_ticket() -> None:
    ticket = _ticket()

    with pytest.raises(InvalidTicketTransitionError):
        ticket.unclaim()


def test_transfer_reassigns_claimant_and_records_event() -> None:
    ticket = _ticket()
    ticket.claim(claimant=TicketActor(discord_user_id="777"))
    ticket.pull_domain_events()
    new_claimant = TicketActor(discord_user_id="888")

    ticket.transfer(new_claimant=new_claimant)

    assert ticket.status == TicketStatus.CLAIMED
    assert ticket.claimed_by_discord_user_id == "888"
    events = ticket.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], TicketTransferred)
    assert events[0].claimed_by_discord_user_id == "888"


def test_transfer_rejects_an_unclaimed_ticket() -> None:
    ticket = _ticket()

    with pytest.raises(InvalidTicketTransitionError):
        ticket.transfer(new_claimant=TicketActor(discord_user_id="888"))


def test_transfer_rejects_a_closed_ticket() -> None:
    ticket = _ticket()
    ticket.claim(claimant=TicketActor(discord_user_id="777"))
    ticket.close(actor=TicketActor(discord_user_id="999"))

    with pytest.raises(InvalidTicketTransitionError):
        ticket.transfer(new_claimant=TicketActor(discord_user_id="888"))
