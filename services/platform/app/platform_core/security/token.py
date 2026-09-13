"""
Token Abstractions: JWT access-token issuance/verification, PyJWT-backed.
Refresh tokens are intentionally opaque random strings looked up against
identity.sessions.refresh_token_hash (per the Physical Schema) rather than
JWTs — they're never parsed client-side, so there's no reason to pay JWT's
encoding overhead or expose their structure.
"""

from __future__ import annotations

import secrets
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


@dataclass(frozen=True, slots=True)
class MfaChallengeClaims:
    subject_user_id: UUID
    org_id: UUID
    challenge_id: UUID
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
            "token_use": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
        }
        return jwt.encode(payload, self._signing_key, algorithm=self._algorithm)

    def verify(self, token: str) -> TokenClaims:
        payload = self._decode(token, expected_use="access")
        return TokenClaims(
            subject_user_id=UUID(payload["sub"]),
            org_id=UUID(payload["org_id"]),
            scopes=tuple(payload.get("scopes", [])),
            expires_at_epoch=payload["exp"],
        )

    def issue_mfa_challenge_token(
        self,
        *,
        user_id: UUID,
        org_id: UUID,
        ttl: timedelta = timedelta(minutes=5),
    ) -> str:
        now = utcnow()
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "org_id": str(org_id),
            "jti": str(UUID(bytes=secrets.token_bytes(16))),
            "token_use": "mfa_challenge",
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
        }
        return jwt.encode(payload, self._signing_key, algorithm=self._algorithm)

    def verify_mfa_challenge_token(self, token: str) -> MfaChallengeClaims:
        payload = self._decode(
            token,
            expected_use="mfa_challenge",
            additional_required_claims=("jti",),
        )
        return MfaChallengeClaims(
            subject_user_id=UUID(payload["sub"]),
            org_id=UUID(payload["org_id"]),
            challenge_id=UUID(payload["jti"]),
            expires_at_epoch=payload["exp"],
        )

    def _decode(
        self,
        token: str,
        *,
        expected_use: str,
        additional_required_claims: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        payload = jwt.decode(
            token,
            self._signing_key,
            algorithms=[self._algorithm],
            options={
                "require": [
                    "sub",
                    "org_id",
                    "exp",
                    "token_use",
                    *additional_required_claims,
                ]
            },
        )
        if payload["token_use"] != expected_use:
            raise jwt.InvalidTokenError(f"Expected a {expected_use} token")
        return payload
