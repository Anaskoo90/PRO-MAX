"""
Application-layer ports: Protocols for infrastructure capabilities the
application layer needs but must not construct or import directly (ADR-005
..009's dependency rule — application depends inward on abstractions,
infrastructure depends outward to satisfy them, never the reverse).

infrastructure.oauth2_client.OAuth2Client satisfies OAuth2ClientPort
structurally (Protocol, no inheritance needed) — composition.py is the only
place that imports the concrete class and wires it in here by type.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.identity.domain.repositories import (
    AuditLogRepository,
    EmailVerificationTokenRepository,
    MfaFactorRepository,
    OrganizationRepository,
    PasswordHistoryRepository,
    PasswordResetTokenRepository,
    PermissionRepository,
    RoleRepository,
    SessionRepository,
    TeamMembershipRepository,
    TeamRepository,
    TrustedDeviceRepository,
    UserRepository,
    UserRoleAssignmentRepository,
)
from app.platform_core.events.publisher import OutboxWriter


class IdentityUnitOfWorkPort(Protocol):
    """What the application layer actually uses off IdentityUnitOfWork —
    satisfied structurally by infrastructure.unit_of_work.IdentityUnitOfWork,
    which application code never imports directly."""

    users: UserRepository
    sessions: SessionRepository
    mfa_factors: MfaFactorRepository
    email_verification_tokens: EmailVerificationTokenRepository
    password_reset_tokens: PasswordResetTokenRepository
    password_history: PasswordHistoryRepository
    organizations: OrganizationRepository
    teams: TeamRepository
    team_memberships: TeamMembershipRepository
    roles: RoleRepository
    permissions: PermissionRepository
    user_role_assignments: UserRoleAssignmentRepository
    trusted_devices: TrustedDeviceRepository
    audit_logs: AuditLogRepository
    outbox: OutboxWriter

    async def __aenter__(self) -> "IdentityUnitOfWorkPort": ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ExternalIdentityPort(Protocol):
    provider_key: str
    subject: str
    email: str | None
    display_name: str | None


class OAuth2ClientPort(Protocol):
    def build_authorization_url(self) -> tuple[str, str]: ...

    async def exchange_code(self, code: str) -> dict[str, Any]: ...

    async def fetch_external_identity(self, token_response: dict[str, Any]) -> ExternalIdentityPort: ...
