# ruff: noqa: F811  -- `http_env` is a fixture imported from tests.http_harness; using it as a test argument
# is not a redefinition (importing it into a global conftest would boot the whole app for every unit test).
"""HTTP-level behavior of authentication for suspended/deactivated organizations
(real app, real routes, real database).

Pins: a suspended/deactivated organization is refused with HTTP 403 and the
dedicated ORGANIZATION_NOT_ACTIVE code; nothing is disclosed to someone
without valid credentials; refresh failures never expose token hashes or
internal identifiers; and unrelated authentication responses are unchanged.
"""

from __future__ import annotations

import re

import pytest

from tests.http_harness import API, http_env  # noqa: F401  (http_env is a fixture)

pytestmark = pytest.mark.asyncio(loop_scope="session")

_HEX64 = re.compile(r"[0-9a-fA-F]{64}")


def _assert_no_internal_identifiers(response, *secrets: str) -> None:
    body = response.text
    assert not _HEX64.search(body), f"a lookup hash leaked: {body}"
    for secret in secrets:
        assert secret not in body, f"credential material leaked: {body}"


async def test_an_active_organization_authenticates_normally(http_env) -> None:
    tenant = await http_env.create_tenant("active")

    tokens = await http_env.login_ok(tenant)

    me = await http_env.client.get(f"{API}/users/me", headers=http_env.bearer(tokens))
    assert me.status_code == 200


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_login_to_a_suspended_or_deactivated_organization_is_403_with_a_dedicated_code(
    http_env, operation: str
) -> None:
    tenant = await http_env.create_tenant("login")
    await getattr(http_env, operation)(tenant)

    response = await http_env.login(tenant)

    assert response.status_code == 403
    assert response.json()["code"] == "ORGANIZATION_NOT_ACTIVE"


async def test_the_organization_status_is_not_disclosed_without_the_right_password(http_env) -> None:
    tenant = await http_env.create_tenant("nodisclose")
    await http_env.suspend(tenant)

    response = await http_env.login(tenant, password="not-the-right-password")

    # unchanged pre-existing behavior for bad credentials, and no hint about the status
    assert response.status_code == 422
    assert response.json()["code"] == "UNAUTHORIZED"
    assert "suspend" not in response.text.lower() and "organization" not in response.text.lower()


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_existing_access_tokens_are_rejected_with_401(http_env, operation: str) -> None:
    tenant = await http_env.create_tenant("access")
    tokens = await http_env.login_ok(tenant)
    await getattr(http_env, operation)(tenant)

    response = await http_env.client.get(f"{API}/users/me", headers=http_env.bearer(tokens))

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_refresh_after_suspension_fails_without_exposing_a_token_hash(http_env, operation: str) -> None:
    tenant = await http_env.create_tenant("refresh")
    tokens = await http_env.login_ok(tenant)
    await getattr(http_env, operation)(tenant)  # revokes the session

    response = await http_env.client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 404  # unchanged status; only the identifiers are gone
    _assert_no_internal_identifiers(response, tokens["refresh_token"], str(tenant.user.id))
    assert response.json()["message"] == "Session was not found"


async def test_refresh_with_an_unknown_token_does_not_echo_anything_derived_from_it(http_env) -> None:
    await http_env.create_tenant("unknown")  # a database with data; the token still matches nothing
    bogus = "totally-made-up-refresh-token-value"

    response = await http_env.client.post(f"{API}/auth/refresh", json={"refresh_token": bogus})

    assert response.status_code == 404
    _assert_no_internal_identifiers(response, bogus)


async def test_logout_with_a_revoked_refresh_token_is_still_idempotent(http_env) -> None:
    tenant = await http_env.create_tenant("logout")
    tokens = await http_env.login_ok(tenant)
    await http_env.suspend(tenant)

    response = await http_env.client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 204  # unchanged


async def test_reactivation_restores_login_but_not_the_old_session(http_env) -> None:
    tenant = await http_env.create_tenant("again")
    old = await http_env.login_ok(tenant)
    await http_env.suspend(tenant)
    await http_env.reactivate(tenant)

    old_access = await http_env.client.get(f"{API}/users/me", headers=http_env.bearer(old))
    fresh = await http_env.login_ok(tenant)
    new_access = await http_env.client.get(f"{API}/users/me", headers=http_env.bearer(fresh))

    assert old_access.status_code == 401
    assert new_access.status_code == 200


async def test_another_tenant_is_unaffected_by_a_suspension(http_env) -> None:
    suspended = await http_env.create_tenant("down")
    healthy = await http_env.create_tenant("up")
    tokens = await http_env.login_ok(healthy)

    await http_env.suspend(suspended)

    assert (await http_env.login(suspended)).status_code == 403
    me = await http_env.client.get(f"{API}/users/me", headers=http_env.bearer(tokens))
    assert me.status_code == 200
