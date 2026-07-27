import pytest

from app.identity.domain.exceptions import SystemRoleImmutableError
from app.identity.domain.rbac import Permission, Role
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7


def test_permission_key_combines_resource_and_action() -> None:
    permission = Permission.create(resource="team", action="create", description="Create a team")
    assert permission.key == "team:create"


def test_system_role_cannot_be_renamed() -> None:
    role = Role.create_system_role(name="org_owner", description="Full control")
    with pytest.raises(SystemRoleImmutableError):
        role.rename("not_allowed")


def test_system_role_cannot_grant_permission() -> None:
    role = Role.create_system_role(name="org_owner", description="Full control")
    with pytest.raises(SystemRoleImmutableError):
        role.grant_permission(EntityId(new_uuid7()))


def test_custom_role_grant_and_revoke_permission() -> None:
    role = Role.create_custom_role(org_id=OrgId(new_uuid7()), name="Support Agent")
    permission_id = EntityId(new_uuid7())

    role.grant_permission(permission_id)
    assert permission_id in role.permission_ids

    role.revoke_permission(permission_id)
    assert permission_id not in role.permission_ids


def test_custom_role_rename_succeeds() -> None:
    role = Role.create_custom_role(org_id=OrgId(new_uuid7()), name="Support Agent")
    role.rename("Senior Support Agent")
    assert role.name == "Senior Support Agent"
