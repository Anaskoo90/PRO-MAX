# ruff: noqa: F811  -- `http_env` is a fixture imported from tests.http_harness (see that module's docstring).
"""Discord bot endpoints vs. organization status, over real HTTP.

Every bot operation acts for the organization behind a guild link (or a setup
code). While that organization is suspended or deactivated each one must be
refused with 403 / ORGANIZATION_NOT_ACTIVE and change nothing; after
reactivation they all work again; other tenants are unaffected. The
ticket-by-id endpoints (claim, close, messages, ...) are covered explicitly:
they reach the organization through the ticket's guild link.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from app.discord_integration.application.authorization_helpers import DiscordAuthorization
from app.discord_integration.presentation import deps as discord_deps
from app.main import app, discord_integration_module
from sqlalchemy import text

from tests.discord_integration.unit.fakes import AllowAllPermissionChecker
from tests.http_harness import API, http_env  # noqa: F401  (http_env is a fixture)

pytestmark = pytest.mark.asyncio(loop_scope="session")

_REFUSED = (403, "ORGANIZATION_NOT_ACTIVE")


def _bot() -> dict:
    # the very dependency the bot routes authenticate against, so this follows however the secret is configured
    return {"X-GuildDesk-Bot-Secret": app.dependency_overrides[discord_deps.get_bot_service_secret]()}


@dataclass
class Guild:
    tenant: object
    guild_id: str
    channel_id: str
    category_id: str
    ticket_id: str
    unused_code: str  # issued while the organization was ACTIVE, redeemed later


async def _issue_code(tenant, monkeypatch) -> str:
    service = discord_integration_module.discord_setup_service
    # the harness tenants have no RBAC roles; permission to request a setup code is not what is under test
    monkeypatch.setattr(service, "_authorization", DiscordAuthorization(permission_checker=AllowAllPermissionChecker()))
    return (await service.request_setup_token(org_id=tenant.org_id, requested_by_user_id=tenant.user.id)).raw_code


async def _ok(response, expected: int = 201):
    assert response.status_code == expected, f"{response.request.method} {response.request.url.path}: {response.text}"
    return response.json()["data"] if response.content else None


async def _linked_guild(http_env, tenant, monkeypatch) -> Guild:
    """An ACTIVE organization with a linked guild, a category and an open ticket,
    plus a second setup code kept unused for later."""
    c, tag = http_env.client, uuid.uuid4().hex[:8]
    guild_id, channel_id = f"G-{tag}", f"CH-{tag}"
    await _ok(await c.post(f"{API}/discord/setup/complete", headers=_bot(), json={
        "code": await _issue_code(tenant, monkeypatch), "discord_guild_id": guild_id,
        "discord_guild_name": "Guild", "discord_user_id": "U1"}))
    category = await _ok(await c.post(f"{API}/discord/guilds/{guild_id}/ticket-categories", headers=_bot(), json={
        "discord_guild_id": guild_id, "name": "Support", "discord_category_channel_id": f"CC-{tag}"}))
    ticket = await _ok(await c.post(f"{API}/discord/tickets", headers=_bot(), json={
        "category_id": category["id"], "discord_guild_id": guild_id, "discord_channel_id": channel_id,
        "title": "Help", "opener_discord_user_id": "U9"}))
    return Guild(tenant=tenant, guild_id=guild_id, channel_id=channel_id, category_id=category["id"],
                 ticket_id=ticket["id"], unused_code=await _issue_code(tenant, monkeypatch))


def _every_bot_operation(http_env, g: Guild) -> dict:
    """Every guild- and ticket-facing bot route, as zero-arg coroutine factories."""
    c, h, P = http_env.client, _bot(), API
    tid, ch = g.ticket_id, g.channel_id
    new_guild = f"G2-{uuid.uuid4().hex[:8]}"
    return {
        "guild status": lambda: c.get(f"{P}/discord/guilds/{g.guild_id}/status", headers=h),
        "complete setup (code issued earlier)": lambda: c.post(f"{P}/discord/setup/complete", headers=h, json={
            "code": g.unused_code, "discord_guild_id": new_guild, "discord_guild_name": "Two", "discord_user_id": "U1"}),
        "list categories": lambda: c.get(f"{P}/discord/guilds/{g.guild_id}/ticket-categories", headers=h),
        "create category": lambda: c.post(f"{P}/discord/guilds/{g.guild_id}/ticket-categories", headers=h, json={
            "discord_guild_id": g.guild_id, "name": f"Cat-{uuid.uuid4().hex[:6]}", "discord_category_channel_id": "CC9"}),
        "create ticket": lambda: c.post(f"{P}/discord/tickets", headers=h, json={
            "category_id": g.category_id, "discord_guild_id": g.guild_id,
            "discord_channel_id": f"CHX-{uuid.uuid4().hex[:6]}", "title": "New", "opener_discord_user_id": "U9"}),
        "ticket by channel": lambda: c.get(f"{P}/discord/tickets/by-channel/{ch}", headers=h),
        "claim (by ticket id)": lambda: c.post(f"{P}/discord/tickets/{tid}/claim", headers=h, json={"claimant_discord_user_id": "S1"}),
        "unclaim (by ticket id)": lambda: c.post(f"{P}/discord/tickets/{tid}/unclaim", headers=h),
        "transfer (by ticket id)": lambda: c.post(f"{P}/discord/tickets/{tid}/transfer", headers=h, json={"new_claimant_discord_user_id": "S2"}),
        "close (by ticket id)": lambda: c.post(f"{P}/discord/tickets/{tid}/close", headers=h, json={"closed_by_discord_user_id": "S1"}),
        "add message (by ticket id)": lambda: c.post(f"{P}/discord/tickets/{tid}/messages", headers=h, json={
            "body": "hi", "author_discord_user_id": "S1", "discord_message_id": f"M-{uuid.uuid4().hex[:8]}"}),
        "list messages (by ticket id)": lambda: c.get(f"{P}/discord/tickets/{tid}/messages", headers=h),
        "add message (by channel)": lambda: c.post(f"{P}/discord/tickets/by-channel/{ch}/messages", headers=h, json={
            "body": "hi", "author_discord_user_id": "S1", "discord_message_id": f"M-{uuid.uuid4().hex[:8]}"}),
        "upload attachment (by channel)": lambda: c.post(
            f"{P}/discord/tickets/by-channel/{ch}/attachments", headers=h,
            files={"file": ("note.txt", b"hello", "text/plain")},
            data={"uploaded_by_discord_user_id": "S1", "discord_attachment_id": f"A-{uuid.uuid4().hex[:8]}"}),
    }


async def _link_count(http_env, tenant) -> int:
    async with http_env.make_uow() as uow:
        return (await uow.session.execute(
            text("SELECT count(*) FROM discord_integration.guild_links WHERE org_id = :o"), {"o": tenant.org_id}
        )).scalar_one()


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_every_bot_operation_is_refused_for_a_suspended_or_deactivated_organization(
    http_env, monkeypatch, operation: str
) -> None:
    tenant = await http_env.create_tenant("bot")
    guild = await _linked_guild(http_env, tenant, monkeypatch)
    operations = _every_bot_operation(http_env, guild)
    for name, call in operations.items():  # control: all of them work while ACTIVE (except the one-shot setup code)
        if name in {"complete setup (code issued earlier)", "close (by ticket id)", "transfer (by ticket id)"}:
            continue
        assert (await call()).status_code < 300, f"{name} should work while the organization is ACTIVE"

    await getattr(http_env, operation)(tenant)

    leaked = {}
    for name, call in operations.items():
        response = await call()
        if (response.status_code, response.json().get("code")) != _REFUSED:
            leaked[name] = f"{response.status_code} {response.text[:120]}"
    assert not leaked, f"bot operations that were NOT refused for a {operation}ed organization: {leaked}"


async def test_a_refused_setup_leaves_no_link_and_does_not_burn_the_code(http_env, monkeypatch) -> None:
    tenant = await http_env.create_tenant("setup")
    guild = await _linked_guild(http_env, tenant, monkeypatch)
    assert await _link_count(http_env, tenant) == 1
    await http_env.suspend(tenant)
    body = {"code": guild.unused_code, "discord_guild_id": "G-new", "discord_guild_name": "N", "discord_user_id": "U1"}

    refused = await http_env.client.post(f"{API}/discord/setup/complete", headers=_bot(), json=body)

    assert (refused.status_code, refused.json()["code"]) == _REFUSED
    assert await _link_count(http_env, tenant) == 1  # nothing was linked
    await http_env.reactivate(tenant)
    redeemed = await http_env.client.post(f"{API}/discord/setup/complete", headers=_bot(), json=body)
    assert redeemed.status_code == 201, redeemed.text  # the same code still works
    assert await _link_count(http_env, tenant) == 2


async def test_bot_operations_resume_after_reactivation(http_env, monkeypatch) -> None:
    tenant = await http_env.create_tenant("resume")
    guild = await _linked_guild(http_env, tenant, monkeypatch)
    await http_env.suspend(tenant)
    assert (await http_env.client.get(f"{API}/discord/guilds/{guild.guild_id}/status", headers=_bot())).status_code == 403

    await http_env.reactivate(tenant)

    c, h = http_env.client, _bot()
    status = await c.get(f"{API}/discord/guilds/{guild.guild_id}/status", headers=h)
    assert status.status_code == 200 and status.json()["data"]["linked"] is True
    assert (await c.get(f"{API}/discord/guilds/{guild.guild_id}/ticket-categories", headers=h)).status_code == 200
    assert (await c.get(f"{API}/discord/tickets/by-channel/{guild.channel_id}", headers=h)).status_code == 200
    operations = _every_bot_operation(http_env, guild)
    for name in ("create category", "create ticket", "claim (by ticket id)", "transfer (by ticket id)",
                 "add message (by ticket id)", "add message (by channel)", "list messages (by ticket id)",
                 "upload attachment (by channel)", "unclaim (by ticket id)", "close (by ticket id)",
                 "complete setup (code issued earlier)"):
        response = await operations[name]()
        assert response.status_code < 300, f"{name} after reactivation: {response.status_code} {response.text[:160]}"


async def test_other_tenants_are_unaffected_by_a_suspension(http_env, monkeypatch) -> None:
    down = await _linked_guild(http_env, await http_env.create_tenant("down"), monkeypatch)
    up = await _linked_guild(http_env, await http_env.create_tenant("up"), monkeypatch)

    await http_env.suspend(down.tenant)

    assert (await http_env.client.get(f"{API}/discord/guilds/{down.guild_id}/status", headers=_bot())).status_code == 403
    for name in ("guild status", "list categories", "create ticket", "claim (by ticket id)",
                 "add message (by ticket id)", "ticket by channel", "close (by ticket id)"):
        response = await _every_bot_operation(http_env, up)[name]()
        assert response.status_code < 300, f"{name} for the healthy tenant: {response.status_code} {response.text[:160]}"


async def test_the_guild_admin_can_still_unlink_a_suspended_tenant_and_link_the_server_elsewhere(
    http_env, monkeypatch
) -> None:
    suspended = await _linked_guild(http_env, await http_env.create_tenant("stuck"), monkeypatch)
    other = await http_env.create_tenant("rescue")
    await http_env.suspend(suspended.tenant)
    rescue_body = {"code": await _issue_code(other, monkeypatch), "discord_guild_id": suspended.guild_id,
                   "discord_guild_name": "Moved", "discord_user_id": "U1"}
    blocked = await http_env.client.post(f"{API}/discord/setup/complete", headers=_bot(), json=rescue_body)
    assert blocked.status_code != 201  # still linked to the suspended tenant

    unlink = await http_env.client.post(
        f"{API}/discord/guilds/{suspended.guild_id}/unlink", headers=_bot(), json={"discord_user_id": "U1"}
    )

    assert unlink.status_code < 300, unlink.text
    relink = await http_env.client.post(
        f"{API}/discord/setup/complete", headers=_bot(),
        json={**rescue_body, "code": await _issue_code(other, monkeypatch)},
    )
    assert relink.status_code == 201, relink.text
