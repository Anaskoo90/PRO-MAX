"""
Token Abstractions: JWT access-token issuance/verification, PyJWT-backed.
Refresh tokens are intentionally opaque random strings looked up against
identity.sessions.refresh_token_hash (per the Physical Schema) rather than
JWTs — they're never parsed client-side, so there's no reason to pay JWT's
encoding overhead or expose their structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

import jwt

from app.platform_core.shared_kernel.utils import utcnow


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject_user_id: UUID
    org_id: UUID
    scopes: tuple[str, ...]
    expires_at_epoch: int


class JwtTokenService:
    def __init__(self, *, signing_key: str, algorithm: str = "HS256") -> None:
        self._signing_key = signing_key
        self._algorithm = algorithm

    def issue_access_token(
        self,
        *,
        user_id: UUID,
        org_id: UUID,
        scopes: list[str],
        ttl: timedelta = timedelta(minutes=15),
    ) -> str:
        now = utcnow()
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "org_id": str(org_id),
            "scopes": scopes,
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
        }
        return jwt.encode(payload, self._signing_key, algorithm=self._algorithm)

    def verify(self, token: str) -> TokenClaims:
        payload = jwt.decode(token, self._signing_key, algorithms=[self._algorithm])
        return TokenClaims(
            subject_user_id=UUID(payload["sub"]),
            org_id=UUID(payload["org_id"]),
            scopes=tuple(payload.get("scopes", [])),
            expires_at_epoch=payload["exp"],
        )
