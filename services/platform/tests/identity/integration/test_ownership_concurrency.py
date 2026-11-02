"""Concurrency tests for ownership-sensitive operations (Milestone 4).

Unlike the rest of the integration suite these use *independent, committed*
database sessions instead of one rolled-back session, because row locks and
conflicting writes only exist between separate transactions. They are
deterministic: an asyncio gate pauses the first operation AFTER its guard
checks and BEFORE its write (while it holds whatever locks it took), the
second operation is started and given time to either run into the lock or,
absent locking, race through, and only then is the first released.

Everything the tests create (organizations, users, a uniquely named owner
role) is deleted afterwards, so they leave the shared test database as they
found it.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.application.rbac_management import PermissionCatalogService, RoleService
from app.identity.application.user_management import UserManagementService
from app.identity.domain.entities import User, UserStatus
from app.identity.domain.exceptions import (
    InvalidOwnershipTransferTargetError,
    NotOrganizationOwnerError,
    OrganizationOwnerProtectedError,
)
from app.identity.domain.organization import Organization
from app.identity.domain.rbac import Role, UserRoleAssignment
from app.identity.domain.value_objects import Email
from app.identity.infrastructure.organization_repository import SqlAlchemyOrganizationRepository
from app.identity.infrastructure.rbac_repositories import SqlAlchemyUserRoleAssignmentRepository
from app.identity.infrastructure.repositories import SqlAlchemyUserRepository
from app.identity.infrastructure.unit_of_work import IdentityUnitOfWork
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.identity.integration.conftest import TEST_DATABASE_URL
from tests.identity.unit.fakes import FakeAuditRecordSink

pytestmark = pytest.mark.asyncio

_PASSWORD = "Correct-Horse-Battery-9"
_SETTLE_SECONDS = 0.5  # time given to the second operation to hit the lock (or race through without one)


# --------------------------------------------------------------------------- fixtures


@dataclass
class _Env:
    make_uow: object
    owner_role_name: str
    org_ids: list = field(default_factory=list)
    role_ids: list = field(default_factory=list)

    def organizations(self) -> OrganizationManagementService:
        return OrganizationManagementService(
            uow_factory=self.make_uow,
            password_hasher=PasswordHashingService(),
            dispatcher=EventDispatcher(),
            owner_system_role_name=self.owner_role_name,
        )

    def roles(self) -> RoleService:
        return RoleService(
            uow_factory=self.make_uow,
            dispatcher=EventDispatcher(),
            permission_catalog=PermissionCatalogService(uow_factory=self.make_uow),
            owner_role_name=self.owner_role_name,
        )

    def users(self) -> UserManagementService:
        return UserManagementService(
            uow_factory=self.make_uow,
            password_hasher=PasswordHashingService(),
            dispatcher=EventDispatcher(),
            audit_logger=AuditLogger(FakeAuditRecordSink()),
            file_storage=None,
        )


@dataclass
class _Org:
    org_id: OrgId
    owner: User  # the designated owner, holds the owner role
    admin: User
    other: User
    owner_role: Role


def _active_user(org_id: OrgId, tag: str) -> User:
    user = User.register(
        org_id=org_id,
        email=Email(f"{tag}-{uuid.uuid4().hex[:10]}@example.com"),
        password_hash=PasswordHashingService().hash(_PASSWORD),
        display_name=tag,
    )
    user.verify_email()
    return user


async def _bootstrap(env: _Env, *, admin_is_co_owner: bool = False) -> _Org:
    async with env.make_uow() as uow:
        owner_role = await uow.roles.get_by_name(None, env.owner_role_name)
        if owner_role is None:
            owner_role = Role.create_system_role(name=env.owner_role_name, description="test owner role")
            await uow.roles.add(owner_role)
            await uow.flush()
            env.role_ids.append(owner_role.id)
        org = Organization.create(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}", owner_user_id=UserId(new_uuid7()))
        org_id = OrgId(org.id)
        owner = _active_user(org_id, "owner")
        org.owner_user_id = UserId(owner.id)
        await uow.organizations.add(org)
        await uow.flush()
        admin, other = _active_user(org_id, "admin"), _active_user(org_id, "other")
        for user in (owner, admin, other):
            await uow.users.add(user)
        await uow.flush()
        holders = [owner, admin] if admin_is_co_owner else [owner]
        for holder in holders:
            await uow.user_role_assignments.add(
                UserRoleAssignment.create(user_id=holder.id, role_id=owner_role.id, org_id=org_id)
            )
        await uow.commit()
        env.org_ids.append(org.id)
    return _Org(org_id=org_id, owner=owner, admin=admin, other=other, owner_role=owner_role)


async def _cleanup(engine, env: _Env) -> None:
    if not env.org_ids and not env.role_ids:
        return
    org_users = "(SELECT id FROM identity.users WHERE org_id IN :orgs)"
    statements = [
        (f"DELETE FROM identity.sessions WHERE user_id IN {org_users}", "orgs"),
        (f"DELETE FROM identity.password_history WHERE user_id IN {org_users}", "orgs"),
        ("DELETE FROM identity.user_roles WHERE org_id IN :orgs", "orgs"),
        ("DELETE FROM identity.organization_invitations WHERE org_id IN :orgs", "orgs"),
        ("DELETE FROM identity.audit_logs WHERE org_id IN :orgs", "orgs"),
        ("DELETE FROM identity.outbox_messages WHERE org_id IN :orgs", "orgs"),
        ("DELETE FROM identity.users WHERE org_id IN :orgs", "orgs"),
        ("DELETE FROM identity.organizations WHERE id IN :orgs", "orgs"),
        ("DELETE FROM identity.role_permissions WHERE role_id IN :roles", "roles"),
        ("DELETE FROM identity.roles WHERE id IN :roles", "roles"),
    ]
    for sql, kind in statements:
        ids = env.org_ids if kind == "orgs" else env.role_ids
        if not ids:
            continue
        try:
            async with engine.begin() as connection:
                await connection.execute(text(sql).bindparams(bindparam(kind, value=ids, expanding=True)))
        except Exception:  # best effort: never mask the test outcome with a cleanup failure
            pass


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect():
            pass
    except Exception:
        await engine.dispose()
        pytest.skip(f"No reachable test database at {TEST_DATABASE_URL}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    environment = _Env(
        make_uow=lambda: IdentityUnitOfWork(session_factory),
        owner_role_name=f"org_owner_{uuid.uuid4().hex[:12]}",
    )
    yield environment
    await _cleanup(engine, environment)
    await engine.dispose()


# --------------------------------------------------------------------------- helpers


class _Gate:
    """Pauses the FIRST call of a patched method (after the caller's guard
    checks, before its write) until released."""

    def __init__(self) -> None:
        self.reached = asyncio.Event()
        self.release = asyncio.Event()
        self._tripped = False

    def wrap(self, original, *, only_if=lambda *_a, **_k: True):
        async def wrapper(*args, **kwargs):
            if not self._tripped and only_if(*args, **kwargs):
                self._tripped = True
                self.reached.set()
                await asyncio.wait_for(self.release.wait(), 20)
            return await original(*args, **kwargs)

        return wrapper


async def _race(gate: _Gate, first, second):
    """Start `first` (it parks at the gate), start `second` while `first` is
    parked, give `second` time to run into a lock (or race through), then
    release `first` and collect both outcomes."""
    task_first = asyncio.create_task(first())
    await asyncio.wait_for(gate.reached.wait(), 20)
    task_second = asyncio.create_task(second())
    await asyncio.sleep(_SETTLE_SECONDS)
    gate.release.set()
    return await asyncio.gather(task_first, task_second, return_exceptions=True)


async def _assert_org_has_a_valid_owner(env: _Env, scenario: _Org) -> User:
    """THE invariant: the designated owner exists, is ACTIVE and holds the
    owner role."""
    async with env.make_uow() as uow:
        org = await uow.organizations.get_by_id(scenario.org_id)
        owner = await uow.users.get_by_id(org.owner_user_id)
        assert owner is not None and owner.org_id == scenario.org_id
        assert owner.status == UserStatus.ACTIVE, "designated owner is not active"
        assert await uow.user_role_assignments.get(owner.id, scenario.owner_role.id) is not None, (
            "designated owner does not hold the owner role"
        )
        return owner


async def _owner_role_holders(env: _Env, scenario: _Org) -> set:
    async with env.make_uow() as uow:
        return {
            user.id
            for user in (scenario.owner, scenario.admin, scenario.other)
            if await uow.user_role_assignments.get(user.id, scenario.owner_role.id) is not None
        }


def _gate_on(monkeypatch, cls, name: str, **wrap_kwargs) -> _Gate:
    gate = _Gate()
    monkeypatch.setattr(cls, name, gate.wrap(getattr(cls, name), **wrap_kwargs))
    return gate


# --------------------------------------------------------------------------- R4a


async def test_r4a_two_concurrent_transfers_cannot_both_succeed(env, monkeypatch) -> None:
    scenario = await _bootstrap(env)
    gate = _gate_on(monkeypatch, SqlAlchemyOrganizationRepository, "update")
    service = env.organizations()

    first, second = await _race(
        gate,
        lambda: service.transfer_ownership(
            org_id=scenario.org_id, new_owner_user_id=scenario.admin.id, actor_user_id=scenario.owner.id
        ),
        lambda: service.transfer_ownership(
            org_id=scenario.org_id, new_owner_user_id=scenario.other.id, actor_user_id=scenario.owner.id
        ),
    )

    assert not isinstance(first, Exception), first
    # the loser re-reads under the lock, finds the actor is no longer the owner
    assert isinstance(second, NotOrganizationOwnerError), second
    owner = await _assert_org_has_a_valid_owner(env, scenario)
    assert owner.id == scenario.admin.id
    assert await _owner_role_holders(env, scenario) == {scenario.admin.id}
    async with env.make_uow() as uow:
        assert (await uow.organizations.get_by_id(scenario.org_id)).version == 2  # exactly one write


# --------------------------------------------------------------------------- R4b


async def test_r4b_revoking_the_owner_role_cannot_race_a_transfer_to_the_same_user(env, monkeypatch) -> None:
    scenario = await _bootstrap(env, admin_is_co_owner=True)
    gate = _gate_on(monkeypatch, SqlAlchemyUserRoleAssignmentRepository, "delete")

    revoke, transfer = await _race(
        gate,
        # the owner revokes the co-owner's role: admin is NOT the designated owner when this is checked...
        lambda: env.roles().revoke_role_from_user(
            user_id=scenario.admin.id,
            role_id=scenario.owner_role.id,
            org_id=scenario.org_id,
            actor_user_id=scenario.owner.id,
        ),
        # ...while ownership is being transferred to that very user
        lambda: env.organizations().transfer_ownership(
            org_id=scenario.org_id, new_owner_user_id=scenario.admin.id, actor_user_id=scenario.owner.id
        ),
    )

    assert not isinstance(revoke, Exception), revoke
    assert not isinstance(transfer, Exception), transfer
    owner = await _assert_org_has_a_valid_owner(env, scenario)  # designated owner still holds the role
    assert owner.id == scenario.admin.id
    assert await _owner_role_holders(env, scenario) == {scenario.admin.id}


# --------------------------------------------------------------------------- R4c


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_r4c_a_user_being_made_owner_cannot_be_suspended_or_deactivated_concurrently(
    env, monkeypatch, operation: str
) -> None:
    scenario = await _bootstrap(env)
    gate = _gate_on(monkeypatch, SqlAlchemyOrganizationRepository, "update")  # parks the transfer after its checks

    transfer, removal = await _race(
        gate,
        lambda: env.organizations().transfer_ownership(
            org_id=scenario.org_id, new_owner_user_id=scenario.admin.id, actor_user_id=scenario.owner.id
        ),
        (
            (lambda: env.users().suspend(
                org_id=scenario.org_id, user_id=scenario.admin.id, reason="race", actor_user_id=scenario.owner.id
            ))
            if operation == "suspend"
            else (lambda: env.users().deactivate_account(user_id=scenario.admin.id))
        ),
    )

    assert not isinstance(transfer, Exception), transfer
    assert isinstance(removal, OrganizationOwnerProtectedError), removal  # blocked, then refused
    owner = await _assert_org_has_a_valid_owner(env, scenario)
    assert owner.id == scenario.admin.id and owner.status == UserStatus.ACTIVE


async def test_r4c_a_transfer_to_a_user_being_suspended_concurrently_is_refused(env, monkeypatch) -> None:
    scenario = await _bootstrap(env)
    gate = _gate_on(
        monkeypatch,
        SqlAlchemyUserRepository,
        "update",
        only_if=lambda _self, user: user.status == UserStatus.SUSPENDED,
    )

    suspension, transfer = await _race(
        gate,
        lambda: env.users().suspend(
            org_id=scenario.org_id, user_id=scenario.admin.id, reason="race", actor_user_id=scenario.owner.id
        ),
        lambda: env.organizations().transfer_ownership(
            org_id=scenario.org_id, new_owner_user_id=scenario.admin.id, actor_user_id=scenario.owner.id
        ),
    )

    assert not isinstance(suspension, Exception), suspension
    assert isinstance(transfer, InvalidOwnershipTransferTargetError), transfer
    owner = await _assert_org_has_a_valid_owner(env, scenario)
    assert owner.id == scenario.owner.id  # ownership never moved to the suspended user
    async with env.make_uow() as uow:
        assert (await uow.users.get_by_id(scenario.admin.id)).status == UserStatus.SUSPENDED


# --------------------------------------------------------------------------- database-enforced version check


async def test_stale_organization_update_is_rejected_by_the_database(env) -> None:
    # Already-committed staleness; the old Python-side compare caught this one
    # too. The overlapping-writers test below is the case it could not.
    scenario = await _bootstrap(env)
    async with env.make_uow() as first_session, env.make_uow() as second_session:
        first = await first_session.organizations.get_by_id(scenario.org_id)
        second = await second_session.organizations.get_by_id(scenario.org_id)  # same version as `first`
        first.name = "Renamed by first"
        await first_session.organizations.update(first)
        await first_session.commit()

        second.name = "Renamed by second"
        with pytest.raises(ConcurrencyConflictError):
            await second_session.organizations.update(second)

    async with env.make_uow() as uow:
        org = await uow.organizations.get_by_id(scenario.org_id)
        assert org.name == "Renamed by first" and org.version == 2  # no lost update


async def test_overlapping_organization_updates_serialize_and_the_loser_conflicts(env) -> None:
    scenario = await _bootstrap(env)
    async with env.make_uow() as first_session, env.make_uow() as second_session:
        first = await first_session.organizations.get_by_id(scenario.org_id)
        second = await second_session.organizations.get_by_id(scenario.org_id)
        first.name = "first"
        second.name = "second"

        await first_session.organizations.update(first)  # claims the version and holds the row lock
        pending = asyncio.create_task(second_session.organizations.update(second))
        await asyncio.sleep(_SETTLE_SECONDS)
        assert not pending.done(), "second writer should be waiting on the row lock"

        await first_session.commit()
        with pytest.raises(ConcurrencyConflictError):
            await pending

    async with env.make_uow() as uow:
        assert (await uow.organizations.get_by_id(scenario.org_id)).name == "first"
