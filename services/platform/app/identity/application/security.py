"""
Security submodule: brute force protection, IP restrictions, device trust,
suspicious login detection, and the read-side of Audit Logs.

Account Lockout and Session Revocation are *not* reimplemented here — they
already exist on User (Authentication submodule, User.record_failed_login/
is_locked) and AuthenticationService.revoke_session respectively. This
module only adds what Authentication didn't already cover.
"""

from __future__ import annotations

import hashlib
import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.events import SuspiciousLoginDetected
from app.identity.domain.exceptions import BruteForceProtectionTriggeredError, IpAddressRestrictedError
from app.identity.domain.security_entities import TrustedDevice
from app.platform_core.notifications.dispatcher import (
    NotificationChannel,
    NotificationDispatcher,
    NotificationRequest,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import utcnow


class RateLimitStore(Protocol):
    """Backing store for the brute-force sliding window. Production needs a
    shared store across replicas (Redis, via the same client the Messaging
    Foundation's idempotency store already uses) — InMemoryRateLimitStore
    below is single-process only, correct for local dev/tests, not for a
    multi-replica deployment."""

    async def increment_and_get(self, key: str, *, window_seconds: int) -> int: ...


class InMemoryRateLimitStore:
    def __init__(self) -> None:
        self._hits: dict[str, list[datetime]] = {}

    async def increment_and_get(self, key: str, *, window_seconds: int) -> int:
        now = utcnow()
        cutoff = now - timedelta(seconds=window_seconds)
        hits = [t for t in self._hits.get(key, []) if t > cutoff]
        hits.append(now)
        self._hits[key] = hits
        return len(hits)


@dataclass(frozen=True, slots=True)
class BruteForcePolicy:
    max_attempts_per_window: int = 20
    window_seconds: int = 300


class BruteForceGuard:
    def __init__(self, *, store: RateLimitStore, policy: BruteForcePolicy = BruteForcePolicy()) -> None:
        self._store = store
        self._policy = policy

    async def check(self, *, ip_address: str) -> None:
        count = await self._store.increment_and_get(f"login_attempts:{ip_address}", window_seconds=self._policy.window_seconds)
        if count > self._policy.max_attempts_per_window:
            raise BruteForceProtectionTriggeredError(retry_after_seconds=self._policy.window_seconds)


class IpRestrictionChecker:
    def check(self, *, ip_address: str, allowlist: list[str], denylist: list[str]) -> None:
        try:
            addr = ipaddress.ip_address(ip_address)
        except ValueError:
            return  # not a parseable IP (e.g. test/dev placeholder) — nothing to restrict against

        for cidr in denylist:
            if addr in ipaddress.ip_network(cidr, strict=False):
                raise IpAddressRestrictedError(ip_address)

        if allowlist:
            if not any(addr in ipaddress.ip_network(cidr, strict=False) for cidr in allowlist):
                raise IpAddressRestrictedError(ip_address)


def fingerprint_device(*, user_agent: str, accept_language: str) -> str:
    raw = f"{user_agent}|{accept_language}"
    return hashlib.sha256(raw.encode()).hexdigest()


class DeviceTrustService:
    def __init__(self, *, uow_factory) -> None:
        self._uow_factory = uow_factory

    async def is_trusted(self, *, user_id: UserId, fingerprint_hash: str) -> bool:
        async with self._uow_factory() as uow:
            device = await uow.trusted_devices.get_by_fingerprint_hash(user_id, fingerprint_hash)
            return device is not None and device.is_valid()

    async def trust_device(self, *, user_id: UserId, fingerprint_hash: str, label: str) -> None:
        async with self._uow_factory() as uow:
            existing = await uow.trusted_devices.get_by_fingerprint_hash(user_id, fingerprint_hash)
            if existing is not None:
                return
            await uow.trusted_devices.add(
                TrustedDevice.create(user_id=user_id, device_fingerprint_hash=fingerprint_hash, label=label)
            )
            await uow.commit()

    async def list_trusted_devices(self, *, user_id: UserId) -> list[TrustedDevice]:
        async with self._uow_factory() as uow:
            return await uow.trusted_devices.list_for_user(user_id)

    async def revoke_device(self, *, device_id) -> None:
        async with self._uow_factory() as uow:
            await uow.trusted_devices.delete(device_id)
            await uow.commit()


class SuspiciousLoginDetector:
    """A new-IP heuristic: if the login IP hasn't appeared in the user's
    recent active sessions, the login is flagged. Deliberately simple —
    geolocation/ASN-based scoring is a real enhancement but needs a data
    source never selected anywhere in this platform's design."""

    def __init__(self, *, uow_factory) -> None:
        self._uow_factory = uow_factory

    async def is_suspicious(self, *, user_id: UserId, ip_address: str) -> bool:
        async with self._uow_factory() as uow:
            sessions = await uow.sessions.list_active_for_user(user_id)
            known_ips = {s.ip_address for s in sessions}
            return bool(known_ips) and ip_address not in known_ips


class AuditLogQueryService:
    def __init__(self, *, uow_factory) -> None:
        self._uow_factory = uow_factory

    async def list_for_org(self, *, org_id: OrgId, category: AuditEventCategory | None = None, limit: int = 50) -> list[AuditLogRecord]:
        async with self._uow_factory() as uow:
            return await uow.audit_logs.list_for_org(org_id, category=category, limit=limit)


class SecurityService:
    """Facade AuthenticationService calls into during login — kept as one
    injected collaborator rather than four, so login()'s signature doesn't
    grow a parameter per security concern."""

    def __init__(
        self,
        *,
        brute_force_guard: BruteForceGuard,
        ip_restriction_checker: IpRestrictionChecker,
        device_trust_service: DeviceTrustService,
        suspicious_login_detector: SuspiciousLoginDetector,
        uow_factory,
    ) -> None:
        self.brute_force_guard = brute_force_guard
        self.ip_restriction_checker = ip_restriction_checker
        self.device_trust_service = device_trust_service
        self.suspicious_login_detector = suspicious_login_detector
        self._uow_factory = uow_factory

    async def check_login_allowed(self, *, org_id: OrgId, ip_address: str) -> None:
        await self.brute_force_guard.check(ip_address=ip_address)
        async with self._uow_factory() as uow:
            org = await uow.organizations.get_by_id(org_id)
        if org is not None:
            self.ip_restriction_checker.check(
                ip_address=ip_address, allowlist=org.ip_allowlist(), denylist=org.ip_denylist()
            )

    async def record_authentication_audit(self, *, org_id: OrgId, actor_user_id: UUID, action: str, ip_address: str) -> None:
        async with self._uow_factory() as uow:
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id, category=AuditEventCategory.AUTHENTICATION, action=action,
                    actor_user_id=UserId(actor_user_id), resource_type="user", resource_id=str(actor_user_id),
                    ip_address=ip_address,
                )
            )
            await uow.commit()


class SuspiciousLoginNotifier:
    """Subscribed to SuspiciousLoginDetected in composition.py, same
    event-dispatcher pattern used to decouple Email Verification from User
    Management — this module doesn't need to be called directly by
    AuthenticationService, only to react to what it publishes."""

    def __init__(self, *, uow_factory, notification_dispatcher: NotificationDispatcher) -> None:
        self._uow_factory = uow_factory
        self._notification_dispatcher = notification_dispatcher

    async def on_suspicious_login_detected(self, event: SuspiciousLoginDetected) -> None:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(EntityId(event.aggregate_id))
        if user is None:
            return
        await self._notification_dispatcher.dispatch(
            NotificationRequest(
                org_id=user.org_id,
                channel=NotificationChannel.EMAIL,
                recipient=str(user.email),
                subject="New sign-in to your GuildDesk account",
                body=f"A new sign-in was detected from IP address {event.ip_address}. "
                "If this wasn't you, reset your password immediately.",
            )
        )
