import pytest
from app.identity.application.rbac_management import PermissionCatalogService, RoleService
from app.identity.domain.entities import User
from app.identity.domain.exceptions import (
    InsufficientAuthorityError,
    OrganizationOwnerProtectedError,
    RoleInUseError,
    RoleNotFoundError,
    UserNotFoundError,
)
from app.identity.domain.organization import Organization
from app.identity.domain.rbac import Permission, Role, UserRoleAssignment
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId, UserId
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


# --- H2 regression: authority limits and owner protection -----------------


async def _permission(uow: FakeUnitOfWork, resource: str, action: str) -> Permission:
    permission = Permission.create(resource=resource, action=action, description=f"{resource}:{action}")
    await uow.permissions.add(permission)
    return permission


async def _actor_holding(uow: FakeUnitOfWork, org_id: OrgId, *permissions: Permission, name: str = "actor-role") -> User:
    """A same-org user whose only authority is a custom role carrying exactly
    `permissions`."""
    actor = _make_member(org_id, email=f"actor-{new_uuid7()}@example.com")
    role = Role.create_custom_role(org_id=org_id, name=f"{name}-{new_uuid7()}")
    for permission in permissions:
        role.grant_permission(permission.id)
    await uow.users.add(actor)
    await uow.roles.add(role)
    await uow.user_role_assignments.add(UserRoleAssignment.create(user_id=actor.id, role_id=role.id, org_id=org_id))
    return actor


async def test_assign_role_rejects_a_role_with_permissions_the_actor_lacks() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    read, write = await _permission(uow, "project", "read"), await _permission(uow, "project", "write")
    actor = await _actor_holding(uow, org_id, read)
    target = _make_member(org_id, email="target@example.com")
    stronger = Role.create_custom_role(org_id=org_id, name="stronger")
    stronger.grant_permission(read.id)
    stronger.grant_permission(write.id)
    await uow.users.add(target)
    await uow.roles.add(stronger)

    with pytest.raises(InsufficientAuthorityError):
        await _make_service(uow).assign_role_to_user(
            user_id=target.id, role_id=stronger.id, org_id=org_id, actor_user_id=actor.id
        )

    assert await uow.user_role_assignments.get(target.id, stronger.id) is None


async def test_assign_role_allows_a_role_within_the_actors_own_permissions() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    read, write = await _permission(uow, "project", "read"), await _permission(uow, "project", "write")
    actor = await _actor_holding(uow, org_id, read, write)
    target = _make_member(org_id, email="target@example.com")
    narrower = Role.create_custom_role(org_id=org_id, name="narrower")
    narrower.grant_permission(read.id)
    await uow.users.add(target)
    await uow.roles.add(narrower)

    await _make_service(uow).assign_role_to_user(
        user_id=target.id, role_id=narrower.id, org_id=org_id, actor_user_id=actor.id
    )

    assert await uow.user_role_assignments.get(target.id, narrower.id) is not None


async def test_assign_role_counts_permissions_inherited_from_a_parent_role() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    read, secret = await _permission(uow, "project", "read"), await _permission(uow, "billing", "manage")
    actor = await _actor_holding(uow, org_id, read)
    target = _make_member(org_id, email="target@example.com")
    parent = Role.create_custom_role(org_id=org_id, name="parent")
    parent.grant_permission(secret.id)
    child = Role.create_custom_role(org_id=org_id, name="child")  # no direct permissions
    child.set_parent(parent.id)
    await uow.users.add(target)
    await uow.roles.add(parent)
    await uow.roles.add(child)

    with pytest.raises(InsufficientAuthorityError):
        await _make_service(uow).assign_role_to_user(
            user_id=target.id, role_id=child.id, org_id=org_id, actor_user_id=actor.id
        )


async def test_org_admin_style_actor_cannot_assign_org_owner_to_themselves() -> None:
    """The audited escalation: org_admin holds role:assign but not
    organization:manage_ownership, and org_owner carries the latter."""
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    role_assign = await _permission(uow, "role", "assign")
    manage_ownership = await _permission(uow, "organization", "manage_ownership")
    admin = await _actor_holding(uow, org_id, role_assign, name="org_admin")
    owner_role = Role.create_system_role(name="org_owner", description="Owner")
    owner_role.permission_ids |= {role_assign.id, manage_ownership.id}  # system roles are seeded, not granted
    await uow.roles.add(owner_role)

    with pytest.raises(InsufficientAuthorityError):
        await _make_service(uow).assign_role_to_user(
            user_id=admin.id, role_id=owner_role.id, org_id=org_id, actor_user_id=admin.id
        )

    assert await uow.user_role_assignments.get(admin.id, owner_role.id) is None


async def test_an_owner_can_assign_the_owner_role() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    role_assign = await _permission(uow, "role", "assign")
    manage_ownership = await _permission(uow, "organization", "manage_ownership")
    owner = await _actor_holding(uow, org_id, role_assign, manage_ownership, name="owner-like")
    target = _make_member(org_id, email="target@example.com")
    owner_role = Role.create_system_role(name="org_owner", description="Owner")
    owner_role.permission_ids |= {role_assign.id, manage_ownership.id}  # system roles are seeded, not granted
    await uow.users.add(target)
    await uow.roles.add(owner_role)

    await _make_service(uow).assign_role_to_user(
        user_id=target.id, role_id=owner_role.id, org_id=org_id, actor_user_id=owner.id
    )

    assert await uow.user_role_assignments.get(target.id, owner_role.id) is not None


async def test_grant_permission_rejects_a_permission_the_actor_does_not_hold() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    read, secret = await _permission(uow, "project", "read"), await _permission(uow, "billing", "manage")
    actor = await _actor_holding(uow, org_id, read)
    role = Role.create_custom_role(org_id=org_id, name="custom")
    await uow.roles.add(role)

    with pytest.raises(InsufficientAuthorityError):
        await _make_service(uow).grant_permission(
            org_id=org_id, role_id=role.id, permission_id=secret.id, actor_user_id=actor.id
        )

    assert secret.id not in role.permission_ids


async def test_grant_permission_allows_a_permission_the_actor_holds() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    read = await _permission(uow, "project", "read")
    actor = await _actor_holding(uow, org_id, read)
    role = Role.create_custom_role(org_id=org_id, name="custom")
    await uow.roles.add(role)

    await _make_service(uow).grant_permission(
        org_id=org_id, role_id=role.id, permission_id=read.id, actor_user_id=actor.id
    )

    assert read.id in role.permission_ids


async def test_set_parent_rejects_a_parent_whose_permissions_exceed_the_actors() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    read, secret = await _permission(uow, "project", "read"), await _permission(uow, "billing", "manage")
    actor = await _actor_holding(uow, org_id, read)
    powerful = Role.create_custom_role(org_id=org_id, name="powerful")
    powerful.grant_permission(secret.id)
    weak = Role.create_custom_role(org_id=org_id, name="weak")
    await uow.roles.add(powerful)
    await uow.roles.add(weak)

    with pytest.raises(InsufficientAuthorityError):
        await _make_service(uow).set_parent(
            org_id=org_id, role_id=weak.id, parent_role_id=powerful.id, actor_user_id=actor.id
        )

    assert weak.parent_role_id is None


async def test_set_parent_allows_a_parent_within_the_actors_permissions() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    read = await _permission(uow, "project", "read")
    actor = await _actor_holding(uow, org_id, read)
    parent = Role.create_custom_role(org_id=org_id, name="parent")
    parent.grant_permission(read.id)
    child = Role.create_custom_role(org_id=org_id, name="child")
    await uow.roles.add(parent)
    await uow.roles.add(child)

    await _make_service(uow).set_parent(
        org_id=org_id, role_id=child.id, parent_role_id=parent.id, actor_user_id=actor.id
    )

    assert child.parent_role_id == parent.id


async def _org_with_owner(uow: FakeUnitOfWork) -> tuple[OrgId, User, Role]:
    """An org whose designated owner holds the seeded-style org_owner role."""
    org_id = OrgId(new_uuid7())
    owner = _make_member(org_id, email="owner@example.com")
    org = Organization.create(name="Acme", slug=f"acme-{new_uuid7().hex[:8]}", owner_user_id=UserId(owner.id))
    org.id = org_id
    owner_role = Role.create_system_role(name="org_owner", description="Owner")
    await uow.organizations.add(org)
    await uow.users.add(owner)
    await uow.roles.add(owner_role)
    await uow.user_role_assignments.add(UserRoleAssignment.create(user_id=owner.id, role_id=owner_role.id, org_id=org_id))
    return org_id, owner, owner_role


async def test_the_designated_owner_cannot_be_stripped_of_the_owner_role() -> None:
    uow = FakeUnitOfWork()
    org_id, owner, owner_role = await _org_with_owner(uow)
    admin = await _actor_holding(uow, org_id)  # no permissions needed: owner role carries none here

    for actor_id in (admin.id, owner.id):  # neither a peer nor the owner themselves
        with pytest.raises(OrganizationOwnerProtectedError):
            await _make_service(uow).revoke_role_from_user(
                user_id=owner.id, role_id=owner_role.id, org_id=org_id, actor_user_id=actor_id
            )

    assert await uow.user_role_assignments.get(owner.id, owner_role.id) is not None


async def test_the_owner_role_can_be_revoked_after_ownership_is_transferred() -> None:
    uow = FakeUnitOfWork()
    org_id, former_owner, owner_role = await _org_with_owner(uow)
    successor = _make_member(org_id, email="successor@example.com")
    await uow.users.add(successor)
    org = await uow.organizations.get_by_id(org_id)
    org.transfer_ownership(UserId(successor.id))  # the dedicated flow
    await uow.organizations.update(org)

    await _make_service(uow).revoke_role_from_user(
        user_id=former_owner.id, role_id=owner_role.id, org_id=org_id, actor_user_id=successor.id
    )

    assert await uow.user_role_assignments.get(former_owner.id, owner_role.id) is None


async def test_revoking_a_role_requires_the_authority_to_have_assigned_it() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    read, secret = await _permission(uow, "project", "read"), await _permission(uow, "billing", "manage")
    weak_actor = await _actor_holding(uow, org_id, read)
    victim = _make_member(org_id, email="victim@example.com")
    strong = Role.create_custom_role(org_id=org_id, name="strong")
    strong.grant_permission(secret.id)
    await uow.users.add(victim)
    await uow.roles.add(strong)
    await uow.user_role_assignments.add(UserRoleAssignment.create(user_id=victim.id, role_id=strong.id, org_id=org_id))

    with pytest.raises(InsufficientAuthorityError):
        await _make_service(uow).revoke_role_from_user(
            user_id=victim.id, role_id=strong.id, org_id=org_id, actor_user_id=weak_actor.id
        )

    assert await uow.user_role_assignments.get(victim.id, strong.id) is not None


async def test_delete_role_is_refused_with_a_conflict_while_an_invitation_references_it() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    role = Role.create_custom_role(org_id=org_id, name="invited-into")
    await uow.roles.add(role)
    uow.organization_invitations.referenced_role_ids.add(role.id)

    with pytest.raises(RoleInUseError):
        await _make_service(uow).delete_role(org_id=org_id, role_id=role.id, actor_user_id=new_uuid7())

    assert await uow.roles.get_by_id(role.id) is not None


async def test_role_in_use_maps_to_http_409() -> None:
    from app.platform_core.errors.handlers import _map_status_code

    assert _map_status_code(RoleInUseError(new_uuid7())) == 409
