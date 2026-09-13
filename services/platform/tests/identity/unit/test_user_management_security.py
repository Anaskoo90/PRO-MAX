from __future__ import annotations

import pytest
from app.identity.application.user_management import UserManagementService
from app.identity.domain.entities import User
from app.identity.domain.exceptions import UserNotFoundError
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.unit.fakes import FakeAuditRecordSink, FakeUnitOfWork

pytestmark = pytest.mark.asyncio


def _make_service(uow: FakeUnitOfWork) -> UserManagementService:
    return UserManagementService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
        file_storage=object(),
    )


async def _add_user(uow: FakeUnitOfWork, org_id: OrgId) -> User:
    user = User.register(
        org_id=org_id,
        email=Email(f"member-{new_uuid7()}@example.com"),
        password_hash="hash",
        display_name="Member",
    )
    await uow.users.add(user)
    return user


@pytest.mark.parametrize("operation", ["suspend", "reactivate"])
async def test_status_mutation_rejects_a_user_owned_by_another_org(
    operation: str,
) -> None:
    uow = FakeUnitOfWork()
    foreign_user = await _add_user(uow, OrgId(new_uuid7()))
    initial_status = foreign_user.status
    caller_org_id = OrgId(new_uuid7())
    actor_user_id = new_uuid7()
    service = _make_service(uow)

    with pytest.raises(UserNotFoundError):
        if operation == "suspend":
            await service.suspend(
                org_id=caller_org_id,
                user_id=foreign_user.id,
                reason="cross-tenant attempt",
                actor_user_id=actor_user_id,
            )
        else:
            await service.reactivate(
                org_id=caller_org_id,
                user_id=foreign_user.id,
                actor_user_id=actor_user_id,
            )

    assert foreign_user.status == initial_status
    assert uow.audit_logs.records == []


async def test_same_tenant_user_status_mutations_work_and_are_audited() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user = await _add_user(uow, org_id)
    actor_user_id = new_uuid7()
    service = _make_service(uow)

    suspended = await service.suspend(
        org_id=org_id,
        user_id=user.id,
        reason="policy violation",
        actor_user_id=actor_user_id,
    )
    reactivated = await service.reactivate(
        org_id=org_id,
        user_id=user.id,
        actor_user_id=actor_user_id,
    )

    assert suspended.status == "suspended"
    assert reactivated.status == "active"
    assert [record.action for record in uow.audit_logs.records] == [
        "user_suspended",
        "user_reactivated",
    ]
    assert all(record.org_id == org_id for record in uow.audit_logs.records)
    assert all(
        record.actor_user_id == actor_user_id for record in uow.audit_logs.records
    )
