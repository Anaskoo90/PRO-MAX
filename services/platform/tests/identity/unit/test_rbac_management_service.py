import pytest
from app.identity.application.rbac_management import PermissionCatalogService, RoleService
from app.identity.domain.entities import User
from app.identity.domain.exceptions import RoleNotFoundError, UserNotFoundError
from app.identity.domain.rbac import Permission, Role
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.unit.fakes import FakeUnitOfWork

pytestmark = pytest.mark.asyncio


def _make_service(uow) -> RoleService:
    return RoleService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(),
        permission_catalog=PermissionCatalogService(uow_factory=lambda: uow),
    )


def _make_member(org_id: OrgId, *, email: str = "member@example.com") -> User:
    return User.register(org_id=org_id, email=Email(email), password_hash="hash", display_name="Member")


async def test_assign_role_to_user_succeeds_for_a_same_org_user_and_custom_role() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user = _make_member(org_id)
    role = Role.create_custom_role(org_id=org_id, name="support")
    await uow.users.add(user)
    await uow.roles.add(role)
    service = _make_service(uow)

    await service.assign_role_to_user(user_id=user.id, role_id=role.id, org_id=org_id, actor_user_id=new_uuid7())

    assignment = await uow.user_role_assignments.get(user.id, role.id)
    assert assignment is not None
    assert uow.outbox.events[-1].payload["event_type"] == "identity.role_assigned_to_user"
    assert uow.outbox.events[-1].org_id == org_id


async def test_assign_role_to_user_allows_a_system_role() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user = _make_member(org_id)
    system_role = Role.create_system_role(name="member", description="Baseline member")
    await uow.users.add(user)
    await uow.roles.add(system_role)
    service = _make_service(uow)

    await service.assign_role_to_user(user_id=user.id, role_id=system_role.id, org_id=org_id, actor_user_id=new_uuid7())

    assert await uow.user_role_assignments.get(user.id, system_role.id) is not None


async def test_assign_role_to_user_rejects_a_role_from_another_org() -> None:
    """An org_admin must not be able to assign another tenant's custom role
    to one of their own users just by guessing/enumerating its id."""
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    user = _make_member(org_id)
    foreign_role = Role.create_custom_role(org_id=other_org_id, name="support")
    await uow.users.add(user)
    await uow.roles.add(foreign_role)
    service = _make_service(uow)

    with pytest.raises(RoleNotFoundError):
        await service.assign_role_to_user(
            user_id=user.id, role_id=foreign_role.id, org_id=org_id, actor_user_id=new_uuid7()
        )


async def test_assign_role_to_user_rejects_a_user_from_another_org() -> None:
    """Likewise, the target user must actually belong to the caller's org —
    otherwise the new assignment's org_id would disagree with the user's
    real organization."""
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    foreign_user = _make_member(other_org_id)
    role = Role.create_custom_role(org_id=org_id, name="support")
    await uow.users.add(foreign_user)
    await uow.roles.add(role)
    service = _make_service(uow)

    with pytest.raises(UserNotFoundError):
        await service.assign_role_to_user(
            user_id=foreign_user.id, role_id=role.id, org_id=org_id, actor_user_id=new_uuid7()
        )


async def test_assign_role_to_user_is_idempotent() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user = _make_member(org_id)
    role = Role.create_custom_role(org_id=org_id, name="support")
    await uow.users.add(user)
    await uow.roles.add(role)
    service = _make_service(uow)

    await service.assign_role_to_user(user_id=user.id, role_id=role.id, org_id=org_id, actor_user_id=new_uuid7())
    await service.assign_role_to_user(user_id=user.id, role_id=role.id, org_id=org_id, actor_user_id=new_uuid7())

    assignments = [a for a in uow.user_role_assignments.assignments if a.user_id == user.id and a.role_id == role.id]
    assert len(assignments) == 1


async def test_revoke_role_from_user_removes_the_assignment() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user = _make_member(org_id)
    role = Role.create_custom_role(org_id=org_id, name="support")
    await uow.users.add(user)
    await uow.roles.add(role)
    service = _make_service(uow)
    await service.assign_role_to_user(user_id=user.id, role_id=role.id, org_id=org_id, actor_user_id=new_uuid7())

    await service.revoke_role_from_user(user_id=user.id, role_id=role.id, org_id=org_id, actor_user_id=new_uuid7())

    assert await uow.user_role_assignments.get(user.id, role.id) is None
    assert uow.outbox.events[-1].payload["event_type"] == "identity.role_revoked_from_user"
    assert uow.outbox.events[-1].org_id == org_id


async def test_revoke_role_from_user_is_a_no_op_for_an_assignment_from_another_org() -> None:
    """Defense in depth: even if a caller somehow knows a valid
    user_id/role_id pair from a different org, revoke must not touch an
    assignment whose org_id doesn't match the caller's own org."""
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    user = _make_member(other_org_id)
    role = Role.create_custom_role(org_id=other_org_id, name="support")
    await uow.users.add(user)
    await uow.roles.add(role)
    other_service = _make_service(uow)
    await other_service.assign_role_to_user(
        user_id=user.id, role_id=role.id, org_id=other_org_id, actor_user_id=new_uuid7()
    )

    service = _make_service(uow)
    await service.revoke_role_from_user(user_id=user.id, role_id=role.id, org_id=org_id, actor_user_id=new_uuid7())

    assert await uow.user_role_assignments.get(user.id, role.id) is not None


async def test_list_roles_for_user_returns_only_that_users_assigned_roles() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user = _make_member(org_id)
    assigned_role = Role.create_custom_role(org_id=org_id, name="support")
    unassigned_role = Role.create_custom_role(org_id=org_id, name="billing")
    await uow.users.add(user)
    await uow.roles.add(assigned_role)
    await uow.roles.add(unassigned_role)
    service = _make_service(uow)
    await service.assign_role_to_user(
        user_id=user.id, role_id=assigned_role.id, org_id=org_id, actor_user_id=new_uuid7()
    )

    roles = await service.list_roles_for_user(user_id=user.id, org_id=org_id)

    assert [r.id for r in roles] == [assigned_role.id]


async def test_list_roles_for_user_returns_empty_for_a_user_with_no_roles() -> None:
    uow = FakeUnitOfWork()
    service = _make_service(uow)

    roles = await service.list_roles_for_user(user_id=new_uuid7(), org_id=OrgId(new_uuid7()))

    assert roles == []


async def test_revoke_role_from_user_is_idempotent_for_an_unknown_assignment() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    service = _make_service(uow)

    await service.revoke_role_from_user(
        user_id=new_uuid7(), role_id=new_uuid7(), org_id=org_id, actor_user_id=new_uuid7()
    )  # must not raise


@pytest.mark.parametrize(
    "operation",
    ["update", "set_parent", "delete", "grant_permission", "revoke_permission"],
)
async def test_role_mutations_reject_a_role_owned_by_another_org(
    operation: str,
) -> None:
    uow = FakeUnitOfWork()
    caller_org_id = OrgId(new_uuid7())
    foreign_org_id = OrgId(new_uuid7())
    foreign_role = Role.create_custom_role(org_id=foreign_org_id, name="foreign")
    permission = Permission.create(
        resource="project", action="read", description="Read projects"
    )
    await uow.roles.add(foreign_role)
    await uow.permissions.add(permission)
    service = _make_service(uow)
    actor_user_id = new_uuid7()

    with pytest.raises(RoleNotFoundError):
        if operation == "update":
            await service.update_role(
                org_id=caller_org_id,
                role_id=foreign_role.id,
                name="compromised",
                actor_user_id=actor_user_id,
            )
        elif operation == "set_parent":
            await service.set_parent(
                org_id=caller_org_id,
                role_id=foreign_role.id,
                parent_role_id=None,
                actor_user_id=actor_user_id,
            )
        elif operation == "delete":
            await service.delete_role(
                org_id=caller_org_id,
                role_id=foreign_role.id,
                actor_user_id=actor_user_id,
            )
        elif operation == "grant_permission":
            await service.grant_permission(
                org_id=caller_org_id,
                role_id=foreign_role.id,
                permission_id=permission.id,
                actor_user_id=actor_user_id,
            )
        else:
            await service.revoke_permission(
                org_id=caller_org_id,
                role_id=foreign_role.id,
                permission_id=permission.id,
                actor_user_id=actor_user_id,
            )

    assert foreign_role.name == "foreign"
    assert permission.id not in foreign_role.permission_ids
    assert foreign_role.id in uow.roles.roles


async def test_set_parent_rejects_a_parent_role_owned_by_another_org() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    role = Role.create_custom_role(org_id=org_id, name="child")
    foreign_parent = Role.create_custom_role(
        org_id=OrgId(new_uuid7()), name="foreign-parent"
    )
    await uow.roles.add(role)
    await uow.roles.add(foreign_parent)
    service = _make_service(uow)

    with pytest.raises(RoleNotFoundError):
        await service.set_parent(
            org_id=org_id,
            role_id=role.id,
            parent_role_id=foreign_parent.id,
            actor_user_id=new_uuid7(),
        )

    assert role.parent_role_id is None


async def test_same_tenant_role_mutation_still_succeeds_and_is_audited() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    role = Role.create_custom_role(org_id=org_id, name="child")
    parent = Role.create_custom_role(org_id=org_id, name="parent")
    await uow.roles.add(role)
    await uow.roles.add(parent)
    service = _make_service(uow)
    actor_user_id = new_uuid7()

    result = await service.set_parent(
        org_id=org_id,
        role_id=role.id,
        parent_role_id=parent.id,
        actor_user_id=actor_user_id,
    )

    assert result.parent_role_id == parent.id
    assert uow.audit_logs.records[-1].org_id == org_id
    assert uow.audit_logs.records[-1].actor_user_id == actor_user_id
    assert uow.audit_logs.records[-1].action == "role_parent_updated"
