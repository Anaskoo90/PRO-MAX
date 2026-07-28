"""Unit of Work: one AsyncSession per request/command, one commit — matches
platform_core.shared_kernel.interfaces.UnitOfWork's Protocol structurally."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.identity.infrastructure.audit_repository import SqlAlchemyAuditLogRepository
from app.identity.infrastructure.organization_repository import SqlAlchemyOrganizationRepository
from app.identity.infrastructure.outbox import SqlAlchemyOutboxWriter
from app.identity.infrastructure.rbac_repositories import (
    SqlAlchemyPermissionRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyUserRoleAssignmentRepository,
)
from app.identity.infrastructure.repositories import (
    SqlAlchemyEmailVerificationTokenRepository,
    SqlAlchemyMfaFactorRepository,
    SqlAlchemyPasswordHistoryRepository,
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from app.identity.infrastructure.security_repositories import SqlAlchemyTrustedDeviceRepository
from app.identity.infrastructure.team_repositories import (
    SqlAlchemyTeamMembershipRepository,
    SqlAlchemyTeamRepository,
)


class IdentityUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.users: SqlAlchemyUserRepository | None = None
        self.sessions: SqlAlchemySessionRepository | None = None
        self.mfa_factors: SqlAlchemyMfaFactorRepository | None = None
        self.email_verification_tokens: SqlAlchemyEmailVerificationTokenRepository | None = None
        self.password_reset_tokens: SqlAlchemyPasswordResetTokenRepository | None = None
        self.password_history: SqlAlchemyPasswordHistoryRepository | None = None
        self.organizations: SqlAlchemyOrganizationRepository | None = None
        self.teams: SqlAlchemyTeamRepository | None = None
        self.team_memberships: SqlAlchemyTeamMembershipRepository | None = None
        self.roles: SqlAlchemyRoleRepository | None = None
        self.permissions: SqlAlchemyPermissionRepository | None = None
        self.user_role_assignments: SqlAlchemyUserRoleAssignmentRepository | None = None
        self.trusted_devices: SqlAlchemyTrustedDeviceRepository | None = None
        self.audit_logs: SqlAlchemyAuditLogRepository | None = None
        self.outbox: SqlAlchemyOutboxWriter | None = None

    async def __aenter__(self) -> "IdentityUnitOfWork":
        self.session = self._session_factory()
        self.users = SqlAlchemyUserRepository(self.session)
        self.sessions = SqlAlchemySessionRepository(self.session)
        self.mfa_factors = SqlAlchemyMfaFactorRepository(self.session)
        self.email_verification_tokens = SqlAlchemyEmailVerificationTokenRepository(self.session)
        self.password_reset_tokens = SqlAlchemyPasswordResetTokenRepository(self.session)
        self.password_history = SqlAlchemyPasswordHistoryRepository(self.session)
        self.organizations = SqlAlchemyOrganizationRepository(self.session)
        self.teams = SqlAlchemyTeamRepository(self.session)
        self.team_memberships = SqlAlchemyTeamMembershipRepository(self.session)
        self.roles = SqlAlchemyRoleRepository(self.session)
        self.permissions = SqlAlchemyPermissionRepository(self.session)
        self.user_role_assignments = SqlAlchemyUserRoleAssignmentRepository(self.session)
        self.trusted_devices = SqlAlchemyTrustedDeviceRepository(self.session)
        self.audit_logs = SqlAlchemyAuditLogRepository(self.session)
        self.outbox = SqlAlchemyOutboxWriter(self.session, event_type="identity.integration_event")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self.session is not None
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()

    async def flush(self) -> None:
        """Pushes pending inserts/updates to the DB within the current
        transaction without committing — needed when one aggregate's
        auto-generated/just-assigned id must be visible to a foreign-key
        constraint before a second, dependent object in the same unit of
        work is flushed. SQLAlchemy only auto-orders cross-table INSERTs via
        explicit ORM relationship() cascades; these ORM models intentionally
        have none (see orm_models.py's ADR-005..009 note), so call sites
        with a real FK dependency between two newly-created rows in the same
        commit (e.g. UserManagementService.register() with a User + its
        first PasswordHistoryEntry) must flush between the two adds."""
        assert self.session is not None
        await self.session.flush()

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()

    async def rollback(self) -> None:
        assert self.session is not None
        await self.session.rollback()
