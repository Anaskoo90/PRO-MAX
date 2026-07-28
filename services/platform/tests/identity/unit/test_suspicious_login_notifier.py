"""
Regression tests for SuspiciousLoginNotifier.on_suspicious_login_detected —
covers the bug where a login that legitimately succeeded turned into a 500
because no email provider is configured in this environment (see
app/platform_core/notifications/dispatcher.py's NotificationDispatcher,
which raises NoProviderRegisteredError when no provider is registered for
the requested channel).

Root cause: EventDispatcher.dispatch() deliberately logs and re-raises any
handler exception (by design, so genuinely unexpected handler failures are
never silently lost) — so an unconfigured notification channel, which is
an expected condition in local dev, was indistinguishable from a real bug
and killed the whole request. The fix narrows the catch to exactly
NoProviderRegisteredError inside the one handler that hits this in
practice, leaving EventDispatcher's re-raise behavior untouched for every
other failure mode.
"""

from __future__ import annotations

import structlog.testing
import pytest

from app.identity.application.security import SuspiciousLoginNotifier
from app.identity.domain.entities import User
from app.identity.domain.events import SuspiciousLoginDetected
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.notifications.email_provider import EmailMessage
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.identity.unit.fakes import FakeUnitOfWork


class _RaisingEmailProvider:
    """A configured provider that itself fails for an unrelated reason
    (e.g. the real SMTP/SES integration is down) — distinct from "no
    provider is registered at all"."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def send(self, message: EmailMessage) -> None:
        raise self._exc


def _make_user() -> User:
    return User.register(org_id=OrgId(new_uuid7()), email=Email("victim@example.com"), password_hash="hash", display_name="Victim")


def _make_event(user: User) -> SuspiciousLoginDetected:
    return SuspiciousLoginDetected(aggregate_id=user.id, session_id=new_uuid7(), ip_address="203.0.113.7")


@pytest.mark.asyncio
async def test_missing_email_provider_does_not_raise() -> None:
    """The exact regression: no email provider configured must not turn a
    successful login into an unhandled exception."""
    user = _make_user()
    uow = FakeUnitOfWork()
    await uow.users.add(user)
    notifier = SuspiciousLoginNotifier(uow_factory=lambda: uow, notification_dispatcher=NotificationDispatcher())

    await notifier.on_suspicious_login_detected(_make_event(user))  # must not raise


@pytest.mark.asyncio
async def test_missing_email_provider_logs_a_structured_warning() -> None:
    user = _make_user()
    uow = FakeUnitOfWork()
    await uow.users.add(user)
    notifier = SuspiciousLoginNotifier(uow_factory=lambda: uow, notification_dispatcher=NotificationDispatcher())

    with structlog.testing.capture_logs() as captured:
        await notifier.on_suspicious_login_detected(_make_event(user))

    warnings = [entry for entry in captured if entry.get("event") == "suspicious_login_alert_skipped_no_provider"]
    assert len(warnings) == 1
    assert warnings[0]["log_level"] == "warning"
    assert warnings[0]["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_other_notification_failures_still_propagate() -> None:
    """Only NoProviderRegisteredError is swallowed — a genuinely
    misbehaving (but configured) provider must still surface."""
    user = _make_user()
    uow = FakeUnitOfWork()
    await uow.users.add(user)
    failing_dispatcher = NotificationDispatcher(email_provider=_RaisingEmailProvider(RuntimeError("smtp connection refused")))
    notifier = SuspiciousLoginNotifier(uow_factory=lambda: uow, notification_dispatcher=failing_dispatcher)

    with pytest.raises(RuntimeError, match="smtp connection refused"):
        await notifier.on_suspicious_login_detected(_make_event(user))


@pytest.mark.asyncio
async def test_dispatching_the_event_through_event_dispatcher_does_not_raise_when_no_provider() -> None:
    """End-to-end through the same EventDispatcher.dispatch_all() path
    AuthenticationService.login() actually calls — confirms the login
    event still gets emitted and handled without blowing up the caller,
    exactly the path that previously produced the 500."""
    user = _make_user()
    uow = FakeUnitOfWork()
    await uow.users.add(user)
    notifier = SuspiciousLoginNotifier(uow_factory=lambda: uow, notification_dispatcher=NotificationDispatcher())

    dispatcher = EventDispatcher()
    dispatcher.subscribe(SuspiciousLoginDetected, notifier.on_suspicious_login_detected)

    await dispatcher.dispatch_all([_make_event(user)])  # must not raise


@pytest.mark.asyncio
async def test_unknown_user_is_a_no_op() -> None:
    """Defensive existing behavior (unrelated to this fix): an event for a
    user that can no longer be found is silently skipped, not an error."""
    uow = FakeUnitOfWork()
    notifier = SuspiciousLoginNotifier(uow_factory=lambda: uow, notification_dispatcher=NotificationDispatcher())

    await notifier.on_suspicious_login_detected(
        SuspiciousLoginDetected(aggregate_id=new_uuid7(), session_id=new_uuid7(), ip_address="203.0.113.7")
    )
