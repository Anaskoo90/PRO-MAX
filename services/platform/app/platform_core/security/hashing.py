"""
Hashing Services.

Resolves a standing gap: every prior Security Architecture document flagged
the password-hashing algorithm as undecided. Writing real code forces the
decision — **Argon2id**, via argon2-cffi, is used here (OWASP's current
recommended default: memory-hard, GPU/ASIC-resistant, tunable). This is a
genuine decision made at this layer, not previously ratified by an ADR —
worth a follow-up ADR entry rather than silently treating it as settled.
"""

from __future__ import annotations

import hashlib
import hmac

from argon2 import PasswordHasher as _Argon2PasswordHasher
from argon2.exceptions import VerifyMismatchError


class PasswordHashingService:
    def __init__(self) -> None:
        self._hasher = _Argon2PasswordHasher()

    def hash(self, plaintext_password: str) -> str:
        return self._hasher.hash(plaintext_password)

    def verify(self, plaintext_password: str, hashed_password: str) -> bool:
        try:
            return self._hasher.verify(hashed_password, plaintext_password)
        except VerifyMismatchError:
            return False

    def needs_rehash(self, hashed_password: str) -> bool:
        """True if the hash was made with older/weaker parameters —
        callers should re-hash on next successful login."""
        return self._hasher.check_needs_rehash(hashed_password)


def hash_for_lookup(value: str, *, secret_pepper: str) -> str:
    """Non-password, deterministic hashing (API keys, webhook signing
    secrets) where Argon2's slow, salted design is wrong — these need to be
    looked up by hash in O(1), not verified against a single candidate.
    HMAC-SHA256 with a server-side pepper, not a bare hash, so a leaked
    hash column alone isn't reversible via a rainbow table."""
    return hmac.new(secret_pepper.encode(), value.encode(), hashlib.sha256).hexdigest()
