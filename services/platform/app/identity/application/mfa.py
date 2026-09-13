"""
Multi-Factor Authentication submodule: TOTP, recovery codes, enrollment,
verification, recovery.

TOTP secrets are encrypted at rest (platform_core.security.encryption)
before being persisted — MfaFactor.secret_encrypted is ciphertext, never a
raw secret. Recovery codes are hashed with the same deterministic
HMAC-lookup hash used for tokens (platform_core.security.hashing.hash_for_lookup),
not Argon2 — a login-time recovery-code check needs to look a code up by
hash directly, which Argon2's per-hash salt makes impossible without
brute-forcing against every stored hash.
"""

from __future__ import annotations

import secrets

import jwt
import pyotp

from app.identity.application.authentication import AuthenticationService
from app.identity.application.dtos import AuthTokens
from app.identity.application.security import BruteForceGuard
from app.identity.domain.entities import MfaFactor, MfaFactorType
from app.identity.domain.exceptions import (
    InvalidMfaCodeError,
    MfaAlreadyEnrolledError,
    RecoveryCodeAlreadyUsedError,
    UserNotFoundError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.messaging.idempotency import IdempotencyStore
from app.platform_core.security.encryption import FieldEncryptionService
from app.platform_core.security.hashing import hash_for_lookup
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import EntityId
from app.platform_core.shared_kernel.utils import utcnow

_RECOVERY_CODE_COUNT = 10


class TotpEnrollmentResult:
    __slots__ = ("factor_id", "secret", "provisioning_uri")

    def __init__(self, factor_id: EntityId, secret: str, provisioning_uri: str) -> None:
        self.factor_id = factor_id
        self.secret = secret
        self.provisioning_uri = provisioning_uri


class MfaService:
    def __init__(
        self,
        *,
        uow_factory,
        encryption: FieldEncryptionService,
        dispatcher: EventDispatcher,
        authentication_service: AuthenticationService,
        recovery_code_pepper: str,
        token_service: JwtTokenService,
        challenge_replay_store: IdempotencyStore,
        attempt_guard: BruteForceGuard,
    ) -> None:
        self._uow_factory = uow_factory
        self._encryption = encryption
        self._dispatcher = dispatcher
        self._authentication_service = authentication_service
        self._recovery_code_pepper = recovery_code_pepper
        self._token_service = token_service
        self._challenge_replay_store = challenge_replay_store
        self._attempt_guard = attempt_guard

    async def start_totp_enrollment(self, *, user_id: EntityId) -> TotpEnrollmentResult:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)

            existing = await uow.mfa_factors.list_for_user(user_id)
            if any(f.factor_type == MfaFactorType.TOTP and f.is_verified() for f in existing):
                raise MfaAlreadyEnrolledError("totp")

            secret = pyotp.random_base32()
            factor = MfaFactor.new_totp(user_id=user_id, secret_encrypted=self._encryption.encrypt(secret))
            await uow.mfa_factors.add(factor)
            await uow.commit()

            provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
                name=str(user.email), issuer_name="GuildDesk"
            )
            return TotpEnrollmentResult(factor_id=factor.id, secret=secret, provisioning_uri=provisioning_uri)

    async def confirm_totp_enrollment(self, *, user_id: EntityId, factor_id: EntityId, code: str) -> list[str]:
        """Returns the plaintext one-time recovery codes — the only moment
        they're ever visible; only their hashes are stored."""
        async with self._uow_factory() as uow:
            factor = await uow.mfa_factors.get_by_id(factor_id)
            if factor is None or factor.user_id != user_id or factor.factor_type != MfaFactorType.TOTP:
                raise InvalidMfaCodeError()

            secret = self._encryption.decrypt(factor.secret_encrypted)
            if not pyotp.TOTP(secret).verify(code, valid_window=1):
                raise InvalidMfaCodeError()

            factor.mark_verified()
            await uow.mfa_factors.update(factor)

            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            user.mark_mfa_enabled(MfaFactorType.TOTP)
            await uow.users.update(user)

            raw_codes = [secrets.token_hex(5) for _ in range(_RECOVERY_CODE_COUNT)]
            for raw_code in raw_codes:
                code_hash = hash_for_lookup(raw_code, secret_pepper=self._recovery_code_pepper)
                await uow.mfa_factors.add(MfaFactor.new_recovery_code(user_id=user_id, recovery_code_hash=code_hash))

            events = user.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return raw_codes

    async def regenerate_recovery_codes(self, *, user_id: EntityId) -> list[str]:
        async with self._uow_factory() as uow:
            existing = await uow.mfa_factors.list_for_user(user_id)
            for factor in existing:
                if factor.factor_type == MfaFactorType.RECOVERY_CODE:
                    await uow.mfa_factors.delete(factor.id)

            raw_codes = [secrets.token_hex(5) for _ in range(_RECOVERY_CODE_COUNT)]
            for raw_code in raw_codes:
                code_hash = hash_for_lookup(raw_code, secret_pepper=self._recovery_code_pepper)
                await uow.mfa_factors.add(MfaFactor.new_recovery_code(user_id=user_id, recovery_code_hash=code_hash))
            await uow.commit()
            return raw_codes

    async def disable_mfa(self, *, user_id: EntityId) -> None:
        async with self._uow_factory() as uow:
            factors = await uow.mfa_factors.list_for_user(user_id)
            for factor in factors:
                await uow.mfa_factors.delete(factor.id)

            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            user.mark_mfa_disabled(MfaFactorType.TOTP)
            await uow.users.update(user)
            events = user.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def verify_mfa_challenge(
        self,
        *,
        challenge_token: str,
        code: str,
        ip_address: str,
        device_info: dict | None,
        remember_me: bool,
    ) -> AuthTokens:
        """Completes the two-step login flow started by
        AuthenticationService.login() using its signed, short-lived challenge."""
        try:
            challenge = self._token_service.verify_mfa_challenge_token(challenge_token)
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise InvalidMfaCodeError() from exc

        await self._attempt_guard.check(
            ip_address=ip_address,
            scope=f"mfa_challenge:{challenge.challenge_id}",
        )
        user_id = EntityId(challenge.subject_user_id)
        recovery_factor = None
        valid_code = False

        async with self._uow_factory() as uow:
            factors = await uow.mfa_factors.list_for_user(user_id)

            totp_factor = next(
                (f for f in factors if f.factor_type == MfaFactorType.TOTP and f.is_verified()), None
            )
            if totp_factor is not None and totp_factor.secret_encrypted:
                secret = self._encryption.decrypt(totp_factor.secret_encrypted)
                if pyotp.TOTP(secret).verify(code, valid_window=1):
                    valid_code = True

            if not valid_code:
                code_hash = hash_for_lookup(code, secret_pepper=self._recovery_code_pepper)
                recovery_factor = next(
                    (
                        f
                        for f in factors
                        if f.factor_type == MfaFactorType.RECOVERY_CODE
                        and f.recovery_code_hash == code_hash
                    ),
                    None,
                )
            if recovery_factor is not None and not valid_code:
                if recovery_factor.is_consumed():
                    raise RecoveryCodeAlreadyUsedError()
                valid_code = True

            if not valid_code:
                raise InvalidMfaCodeError()

            replay_ttl = max(1, challenge.expires_at_epoch - int(utcnow().timestamp()))
            is_first_use = await self._challenge_replay_store.check_and_mark(
                f"mfa_challenge:{challenge.challenge_id}", ttl_seconds=replay_ttl
            )
            if not is_first_use:
                raise InvalidMfaCodeError()

            if recovery_factor is not None:
                recovery_factor.mark_consumed()
                await uow.mfa_factors.update(recovery_factor)
                await uow.commit()

        return await self._authentication_service.complete_mfa_challenge(
            user_id=user_id,
            ip_address=ip_address,
            device_info=device_info,
            remember_me=remember_me,
        )
