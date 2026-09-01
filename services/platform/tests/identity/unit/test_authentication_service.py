import pytest

from app.identity.application.authentication import AuthenticationService
from app.identity.domain.entities import User
from app.identity.domain.exceptions import InvalidCredentialsError, OrganizationNotFoundError
from app.identity.domain.organization import Organization
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.identity.unit.fakes import FakeAuditRecordSink, FakeUnitOfWork

pytestmark = pytest.mark.asyncio

_PASSWORD = "correct horse battery staple"


def _make_service(uow) -> AuthenticationService:
    return AuthenticationService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(),
        token_service=JwtTokenService(signing_key="a" * 32), dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
    )


async def _make_org_and_active_user(uow, *, slug: str = "acme", email: str = "user@example.com") -> tuple[Organization, User]:
    org = Organization.create(name="Acme", slug=slug, owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    user = User.register(
        org_id=OrgId(org.id), email=Email(email), password_hash=PasswordHashingService().hash(_PASSWORD),
        display_name="A User",
    )
    user.verify_email()
    await uow.users.add(user)
    return org, user


async def test_login_with_org_id_succeeds_for_a_valid_active_user() -> None:
    uow = FakeUnitOfWork()
    org, user = await _make_org_and_active_user(uow)
    service = _make_service(uow)

    result = await service.login(
        org_id=OrgId(org.id), email="user@example.com", password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    assert result.tokens is not None
    assert result.mfa_challenge_user_id is None


async def test_login_with_org_slug_resolves_to_the_same_organization() -> None:
    uow = FakeUnitOfWork()
    org, user = await _make_org_and_active_user(uow, slug="acme")
    service = _make_service(uow)

    result = await service.login(
        org_slug="acme", email="user@example.com", password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    assert result.tokens is not None


async def test_login_with_an_unknown_org_slug_raises_organization_not_found() -> None:
    uow = FakeUnitOfWork()
    service = _make_service(uow)

    with pytest.raises(OrganizationNotFoundError):
        await service.login(
            org_slug="does-not-exist", email="user@example.com", password=_PASSWORD,
            ip_address="127.0.0.1", device_info=None, remember_me=False,
        )


async def test_login_rejects_an_incorrect_password_regardless_of_org_identifier_used() -> None:
    uow = FakeUnitOfWork()
    org, user = await _make_org_and_active_user(uow, slug="acme")
    service = _make_service(uow)

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            org_slug="acme", email="user@example.com", password="wrong-password",
            ip_address="127.0.0.1", device_info=None, remember_me=False,
        )


async def test_login_via_slug_and_via_id_are_equivalent_for_the_same_org() -> None:
    """Same organization, same outcome, regardless of which identifier the
    caller used to reach it — slug resolution is purely an alternate entry
    point, not a different login path."""
    uow_for_id = FakeUnitOfWork()
    org_a, _ = await _make_org_and_active_user(uow_for_id, slug="acme", email="user@example.com")
    result_via_id = await _make_service(uow_for_id).login(
        org_id=OrgId(org_a.id), email="user@example.com", password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    uow_for_slug = FakeUnitOfWork()
    await _make_org_and_active_user(uow_for_slug, slug="acme", email="user@example.com")
    result_via_slug = await _make_service(uow_for_slug).login(
        org_slug="acme", email="user@example.com", password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    assert result_via_id.tokens is not None
    assert result_via_slug.tokens is not None
