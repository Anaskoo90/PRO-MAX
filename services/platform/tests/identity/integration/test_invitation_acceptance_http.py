# ruff: noqa: F811  -- `http_env` is a fixture imported from tests.http_harness (see that module's docstring).
"""POST /invitations/accept for suspended/deactivated organizations, over real HTTP:
403 + ORGANIZATION_NOT_ACTIVE, no user/membership created, the invitation left
pending, and the same token works after reactivation."""

from __future__ import annotations

import uuid

import pytest
from app.identity.domain.rbac import Role
from app.main import identity_module
from sqlalchemy import text

from tests.http_harness import API, PASSWORD, http_env  # noqa: F401  (http_env is a fixture)

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _Mail:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, message) -> None:
        self.messages.append(message)

    def token(self) -> str:
        body = self.messages[-1].html_body or self.messages[-1].text_body
        return body.split("token=")[1].split('"')[0].split("<")[0].split()[0]


async def _invite(http_env, tenant, monkeypatch):
    """A pending invitation into `tenant`'s organization, issued while it is ACTIVE."""
    mail = _Mail()
    monkeypatch.setattr(identity_module.notification_dispatcher, "_email_provider", mail)
    role = Role.create_custom_role(org_id=tenant.org_id, name=f"invitee-{uuid.uuid4().hex[:8]}")
    async with http_env.make_uow() as uow:  # the harness tenants have no seeded roles
        await uow.roles.add(role)
        await uow.commit()
    email = f"invitee-{uuid.uuid4().hex[:10]}@example.com"
    await identity_module.organization_invitation_service.invite_member(
        org_id=tenant.org_id, email=email, role_id=role.id, invited_by_user_id=tenant.user.id
    )
    return mail.token(), email, role


def _accept(http_env, token: str):
    return http_env.client.post(
        f"{API}/invitations/accept", json={"token": token, "password": PASSWORD, "display_name": "New Member"}
    )


async def _member_count(http_env, tenant, email: str) -> int:
    async with http_env.make_uow() as uow:
        return (
            await uow.session.execute(
                text("SELECT count(*) FROM identity.users WHERE org_id = :o AND email = :e"),
                {"o": tenant.org_id, "e": email},
            )
        ).scalar_one()


async def _pending_invitations(http_env, tenant) -> int:
    async with http_env.make_uow() as uow:
        return len(await uow.organization_invitations.list_pending_for_org(tenant.org_id))


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_accepting_an_invitation_is_refused_with_403_for_an_inactive_organization(
    http_env, monkeypatch, operation: str
) -> None:
    tenant = await http_env.create_tenant("invite")
    token, email, _role = await _invite(http_env, tenant, monkeypatch)
    await getattr(http_env, operation)(tenant)

    response = await _accept(http_env, token)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "ORGANIZATION_NOT_ACTIVE"
    assert await _member_count(http_env, tenant, email) == 0  # no user, no membership
    assert await _pending_invitations(http_env, tenant) == 1  # invitation untouched


async def test_the_same_token_is_accepted_after_reactivation_and_the_new_member_can_log_in(
    http_env, monkeypatch
) -> None:
    tenant = await http_env.create_tenant("reopen")
    token, email, role = await _invite(http_env, tenant, monkeypatch)
    await http_env.suspend(tenant)
    assert (await _accept(http_env, token)).status_code == 403
    await http_env.reactivate(tenant)

    accepted = await _accept(http_env, token)

    assert accepted.status_code == 201, accepted.text
    assert await _member_count(http_env, tenant, email) == 1
    login = await http_env.client.post(
        f"{API}/auth/login", json={"org_slug": tenant.slug, "email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text


async def test_another_tenants_invitation_is_unaffected(http_env, monkeypatch) -> None:
    down = await http_env.create_tenant("down")
    up = await http_env.create_tenant("up")
    up_token, up_email, _ = await _invite(http_env, up, monkeypatch)
    down_token, down_email, _ = await _invite(http_env, down, monkeypatch)

    await http_env.suspend(down)

    assert (await _accept(http_env, down_token)).status_code == 403
    assert (await _accept(http_env, up_token)).status_code == 201
    assert await _member_count(http_env, up, up_email) == 1
    assert await _member_count(http_env, down, down_email) == 0
