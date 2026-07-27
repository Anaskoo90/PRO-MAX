"""
Security Tests: scenarios framed around what an attacker would try, not
just correctness of a single method — privilege escalation via system
roles, session reuse after revocation, weak-password acceptance, and
malformed-input handling that could otherwise open an injection surface.
"""

from __future__ import annotations

import pytest

from app.identity.domain.entities import Session
from app.identity.domain.exceptions import SystemRoleImmutableError
from app.identity.domain.rbac import Role
from app.identity.domain.value_objects import Email, InvalidEmailError
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


def test_system_role_permissions_cannot_be_escalated_by_a_tenant_admin() -> None:
    """A system role (org_owner, org_admin, member) must never be
    mutable through the same code path a tenant admin's custom-role
    management API calls — otherwise any org admin could grant themselves
    platform-wide permissions by editing a system role directly."""
    system_role = Role.create_system_role(name="org_admin", description="Administrative control")

    with pytest.raises(SystemRoleImmutableError):
        system_role.grant_permission(EntityId(new_uuid7()))

    with pytest.raises(SystemRoleImmutableError):
        system_role.set_parent(EntityId(new_uuid7()))


def test_revoked_session_is_not_usable_for_refresh() -> None:
    """A refresh token whose session has been revoked (logout, password
    reset, or explicit device revocation) must never be exchangeable for a
    new access token again."""
    session = Session.create(
        user_id=EntityId(new_uuid7()), refresh_token_hash="hash", device_info=None, ip_address="203.0.113.1",
        remember_me=False,
    )
    assert session.is_active() is True

    session.revoke()

    assert session.is_active() is False


@pytest.mark.parametrize(
    "weak_password",
    ["password", "12345678", "qwertyui", "aaaaaaaaaaaa", "short1!"],
)
def test_common_weak_passwords_are_rejected(weak_password: str) -> None:
    assert DEFAULT_PASSWORD_POLICY.is_valid(weak_password) is False


def test_strong_password_satisfying_every_rule_is_accepted() -> None:
    assert DEFAULT_PASSWORD_POLICY.is_valid("Correct-Horse-Battery-9") is True


@pytest.mark.parametrize(
    "malicious_email",
    [
        "'; DROP TABLE identity.users; --",
        "<script>alert(1)</script>@example.com",
        "no-at-sign.example.com",
        "",
    ],
)
def test_malformed_or_malicious_email_input_is_rejected_at_the_value_object(malicious_email: str) -> None:
    """Email is validated at construction time in the domain layer, before
    it ever reaches a query — parameterized queries (SQLAlchemy) already
    prevent injection, but rejecting garbage at the value object is a
    second, independent layer of defense that also improves data quality."""
    with pytest.raises(InvalidEmailError):
        Email(malicious_email)
