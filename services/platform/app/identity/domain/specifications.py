"""Identity specifications, per the Domain Modeling & DDD Blueprint's
Specification pattern (shared_kernel.validation.Specification)."""

from __future__ import annotations

from app.identity.domain.entities import PasswordHistoryEntry, User
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.validation import Specification


class AccountLockoutSpecification(Specification[User]):
    def is_satisfied_by(self, candidate: User) -> bool:
        return candidate.is_locked()


class PasswordReuseSpecification(Specification[tuple[str, list[PasswordHistoryEntry]]]):
    """Candidate is (plaintext_new_password, recent_history_entries).
    Satisfied (i.e. reuse detected) if the new password matches any of the
    last N stored hashes."""

    def __init__(self, hasher: PasswordHashingService) -> None:
        self._hasher = hasher

    def is_satisfied_by(self, candidate: tuple[str, list[PasswordHistoryEntry]]) -> bool:
        plaintext, history = candidate
        return any(self._hasher.verify(plaintext, entry.password_hash) for entry in history)
