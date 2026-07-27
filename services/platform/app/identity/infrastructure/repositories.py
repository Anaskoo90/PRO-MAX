"""SQLAlchemy-backed implementations of the Identity repository Protocols."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.entities import (
    EmailVerificationToken,
    MfaFactor,
    PasswordHistoryEntry,
    PasswordResetToken,
    Session,
    User,
)
from app.identity.infrastructure import mappers
from app.identity.infrastructure.orm_models import (
    EmailVerificationTokenOrmModel,
    MfaFactorOrmModel,
    PasswordHistoryOrmModel,
    PasswordResetTokenOrmModel,
    SessionOrmModel,
    UserOrmModel,
)
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: EntityId) -> User | None:
        row = await self._session.get(UserOrmModel, user_id)
        return mappers.user_to_domain(row) if row and row.deleted_at is None else None

    async def get_by_email(self, org_id: OrgId, email: str) -> User | None:
        stmt = select(UserOrmModel).where(
            UserOrmModel.org_id == org_id,
            UserOrmModel.email == email,
            UserOrmModel.deleted_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.user_to_domain(row) if row else None

    async def list_by_org(self, org_id: OrgId, *, offset: int = 0, limit: int = 50) -> list[User]:
        stmt = (
            select(UserOrmModel)
            .where(UserOrmModel.org_id == org_id, UserOrmModel.deleted_at.is_(None))
            .order_by(UserOrmModel.created_at)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.user_to_domain(r) for r in rows]

    async def add(self, user: User) -> None:
        self._session.add(mappers.user_to_orm(user))

    async def update(self, user: User) -> None:
        """Optimistic-lock update: `user.version` is the version the
        aggregate was loaded with. If the stored row has since moved past
        it, this is a concurrent modification — raise rather than overwrite."""
        row = await self._session.get(UserOrmModel, user.id)
        if row is None:
            raise ValueError(f"User {user.id} not found for update")
        if row.version != user.version:
            raise ConcurrencyConflictError("User", user.id)
        mappers.user_to_orm(user, row)
        row.version = user.version + 1
        user.version += 1


class SqlAlchemySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, session_id: EntityId) -> Session | None:
        row = await self._session.get(SessionOrmModel, session_id)
        return mappers.session_to_domain(row) if row else None

    async def get_by_refresh_token_hash(self, refresh_token_hash: str) -> Session | None:
        stmt = select(SessionOrmModel).where(SessionOrmModel.refresh_token_hash == refresh_token_hash)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.session_to_domain(row) if row else None

    async def list_active_for_user(self, user_id: EntityId) -> list[Session]:
        stmt = select(SessionOrmModel).where(
            SessionOrmModel.user_id == user_id, SessionOrmModel.revoked_at.is_(None)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.session_to_domain(r) for r in rows]

    async def add(self, session: Session) -> None:
        self._session.add(mappers.session_to_orm(session))

    async def update(self, session: Session) -> None:
        row = await self._session.get(SessionOrmModel, session.id)
        if row is None:
            raise ValueError(f"Session {session.id} not found for update")
        mappers.session_to_orm(session, row)


class SqlAlchemyMfaFactorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, factor_id: EntityId) -> MfaFactor | None:
        row = await self._session.get(MfaFactorOrmModel, factor_id)
        return mappers.mfa_factor_to_domain(row) if row else None

    async def list_for_user(self, user_id: EntityId) -> list[MfaFactor]:
        stmt = select(MfaFactorOrmModel).where(MfaFactorOrmModel.user_id == user_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.mfa_factor_to_domain(r) for r in rows]

    async def add(self, factor: MfaFactor) -> None:
        self._session.add(mappers.mfa_factor_to_orm(factor))

    async def update(self, factor: MfaFactor) -> None:
        row = await self._session.get(MfaFactorOrmModel, factor.id)
        if row is None:
            raise ValueError(f"MfaFactor {factor.id} not found for update")
        mappers.mfa_factor_to_orm(factor, row)

    async def delete(self, factor_id: EntityId) -> None:
        row = await self._session.get(MfaFactorOrmModel, factor_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyEmailVerificationTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token_hash(self, token_hash: str) -> EmailVerificationToken | None:
        stmt = select(EmailVerificationTokenOrmModel).where(
            EmailVerificationTokenOrmModel.token_hash == token_hash
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.email_verification_token_to_domain(row) if row else None

    async def add(self, token: EmailVerificationToken) -> None:
        self._session.add(mappers.email_verification_token_to_orm(token))

    async def update(self, token: EmailVerificationToken) -> None:
        row = await self._session.get(EmailVerificationTokenOrmModel, token.id)
        if row is None:
            raise ValueError(f"EmailVerificationToken {token.id} not found for update")
        mappers.email_verification_token_to_orm(token, row)

    async def invalidate_outstanding_for_user(self, user_id: EntityId) -> None:
        from app.platform_core.shared_kernel.utils import utcnow

        stmt = (
            update(EmailVerificationTokenOrmModel)
            .where(
                EmailVerificationTokenOrmModel.user_id == user_id,
                EmailVerificationTokenOrmModel.consumed_at.is_(None),
            )
            .values(consumed_at=utcnow())
        )
        await self._session.execute(stmt)


class SqlAlchemyPasswordResetTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetTokenOrmModel).where(PasswordResetTokenOrmModel.token_hash == token_hash)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.password_reset_token_to_domain(row) if row else None

    async def add(self, token: PasswordResetToken) -> None:
        self._session.add(mappers.password_reset_token_to_orm(token))

    async def update(self, token: PasswordResetToken) -> None:
        row = await self._session.get(PasswordResetTokenOrmModel, token.id)
        if row is None:
            raise ValueError(f"PasswordResetToken {token.id} not found for update")
        mappers.password_reset_token_to_orm(token, row)

    async def invalidate_outstanding_for_user(self, user_id: EntityId) -> None:
        from app.platform_core.shared_kernel.utils import utcnow

        stmt = (
            update(PasswordResetTokenOrmModel)
            .where(
                PasswordResetTokenOrmModel.user_id == user_id,
                PasswordResetTokenOrmModel.consumed_at.is_(None),
            )
            .values(consumed_at=utcnow())
        )
        await self._session.execute(stmt)


class SqlAlchemyPasswordHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def recent_for_user(self, user_id: EntityId, *, limit: int = 5) -> list[PasswordHistoryEntry]:
        stmt = (
            select(PasswordHistoryOrmModel)
            .where(PasswordHistoryOrmModel.user_id == user_id)
            .order_by(PasswordHistoryOrmModel.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.password_history_to_domain(r) for r in rows]

    async def add(self, entry: PasswordHistoryEntry) -> None:
        self._session.add(mappers.password_history_to_orm(entry))
