"""Security submodule entities: device trust. Account lockout, session
revocation, and brute-force lockout state live on User/Session already
(Authentication submodule) — not duplicated here."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.platform_core.shared_kernel.types import EntityId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class TrustedDevice:
    def __init__(
        self,
        *,
        id: EntityId,
        user_id: UserId,
        device_fingerprint_hash: str,
        label: str,
        trusted_until: datetime,
        created_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.device_fingerprint_hash = device_fingerprint_hash
        self.label = label
        self.trusted_until = trusted_until
        self.created_at = created_at or utcnow()

    @classmethod
    def create(
        cls, *, user_id: UserId, device_fingerprint_hash: str, label: str, ttl: timedelta = timedelta(days=30)
    ) -> "TrustedDevice":
        return cls(
            id=EntityId(new_uuid7()),
            user_id=user_id,
            device_fingerprint_hash=device_fingerprint_hash,
            label=label,
            trusted_until=utcnow() + ttl,
        )

    def is_valid(self) -> bool:
        return self.trusted_until > utcnow()
