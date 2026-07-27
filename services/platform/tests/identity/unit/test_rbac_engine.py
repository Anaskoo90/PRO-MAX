import pytest

from app.identity.application.rbac_engine import PermissionEvaluator, RoleResolutionService
from app.identity.domain.exceptions import InsufficientPermissionError
from app.identity.domain.rbac import Permission, Role, UserRoleAssignment
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.identity.unit.fakes import FakeUnitOfWork


def _make_uow_factory(uow: FakeUnitOfWork):
    return lambda: uow


@pytest.mark.asyncio
async def test_user_with_no_roles_has_no_permission() -> None:
    uow = FakeUnitOfWork()
    permission = Permission.create(resource="team", action="create", description="")
    await uow.permissions.add(permission)

    role_resolution = RoleResolutionService(uow_factory=_make_uow_factory(uow))
    evaluator = PermissionEvaluator(uow_factory=_make_uow_factory(uow), role_resolution=role_resolution)

    org_id = OrgId(new_uuid7())
    user_id = UserId(new_uuid7())
    assert await evaluator.has_permission(user_id=user_id, org_id=org_id, resource="team", action="create") is False


@pytest.mark.asyncio
async def test_directly_assigned_role_grants_its_permission() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user_id = UserId(new_uuid7())

    permission = Permission.create(resource="team", action="create", description="")
    await uow.permissions.add(permission)

    role = Role.create_custom_role(org_id=org_id, name="Team Manager")
    role.grant_permission(permission.id)
    await uow.roles.add(role)
    await uow.user_role_assignments.add(UserRoleAssignment.create(user_id=user_id, role_id=role.id, org_id=org_id))

    role_resolution = RoleResolutionService(uow_factory=_make_uow_factory(uow))
    evaluator = PermissionEvaluator(uow_factory=_make_uow_factory(uow), role_resolution=role_resolution)

    assert await evaluator.has_permission(user_id=user_id, org_id=org_id, resource="team", action="create") is True


@pytest.mark.asyncio
async def test_permission_is_inherited_through_role_hierarchy() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user_id = UserId(new_uuid7())

    permission = Permission.create(resource="organization", action="read", description="")
    await uow.permissions.add(permission)

    parent_role = Role.create_custom_role(org_id=org_id, name="Base Member")
    parent_role.grant_permission(permission.id)
    await uow.roles.add(parent_role)

    child_role = Role.create_custom_role(org_id=org_id, name="Specialist", parent_role_id=parent_role.id)
    await uow.roles.add(child_role)

    await uow.user_role_assignments.add(UserRoleAssignment.create(user_id=user_id, role_id=child_role.id, org_id=org_id))

    role_resolution = RoleResolutionService(uow_factory=_make_uow_factory(uow))
    evaluator = PermissionEvaluator(uow_factory=_make_uow_factory(uow), role_resolution=role_resolution)

    # The user was only assigned the child role, but should inherit the
    # parent role's permission via the hierarchy walk.
    assert await evaluator.has_permission(user_id=user_id, org_id=org_id, resource="organization", action="read") is True


@pytest.mark.asyncio
async def test_assert_permission_raises_and_records_an_audit_denial() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user_id = UserId(new_uuid7())

    role_resolution = RoleResolutionService(uow_factory=_make_uow_factory(uow))
    evaluator = PermissionEvaluator(uow_factory=_make_uow_factory(uow), role_resolution=role_resolution)

    with pytest.raises(InsufficientPermissionError):
        await evaluator.assert_permission(user_id=user_id, org_id=org_id, resource="organization", action="update")

    assert len(uow.audit_logs.records) == 1
    assert uow.audit_logs.records[0].action == "permission_denied"


@pytest.mark.asyncio
async def test_unknown_permission_key_is_never_granted() -> None:
    uow = FakeUnitOfWork()  # no permissions seeded at all
    role_resolution = RoleResolutionService(uow_factory=_make_uow_factory(uow))
    evaluator = PermissionEvaluator(uow_factory=_make_uow_factory(uow), role_resolution=role_resolution)

    result = await evaluator.has_permission(
        user_id=UserId(new_uuid7()), org_id=OrgId(new_uuid7()), resource="nonexistent", action="anything"
    )
    assert result is False
