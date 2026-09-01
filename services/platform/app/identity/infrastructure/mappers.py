"""ORM row <-> domain entity mapping, kept separate from the repository
classes so the translation logic is independently testable."""

from __future__ import annotations

from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.entities import (
    EmailVerificationToken,
    MfaFactor,
    MfaFactorType,
    PasswordHistoryEntry,
    PasswordResetToken,
    Session,
    User,
    UserStatus,
)
from app.identity.domain.invitation import InvitationStatus, OrganizationInvitation
from app.identity.domain.organization import Organization, OrganizationStatus
from app.identity.domain.rbac import Permission, Role, UserRoleAssignment
from app.identity.domain.security_entities import TrustedDevice
from app.identity.domain.team import Team, TeamMembership, TeamRole
from app.identity.domain.value_objects import Email
from app.identity.infrastructure.orm_models import (
    AuditLogOrmModel,
    EmailVerificationTokenOrmModel,
    MfaFactorOrmModel,
    OrganizationInvitationOrmModel,
    OrganizationOrmModel,
    PasswordHistoryOrmModel,
    PasswordResetTokenOrmModel,
    PermissionOrmModel,
    RoleOrmModel,
    SessionOrmModel,
    TeamMembershipOrmModel,
    TeamOrmModel,
    TrustedDeviceOrmModel,
    UserOrmModel,
    UserRoleOrmModel,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def user_to_domain(row: UserOrmModel) -> User:
    return User(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        email=Email(row.email),
        password_hash=row.password_hash,
        status=UserStatus(row.status),
        display_name=row.display_name,
        mfa_enabled=row.mfa_enabled,
        failed_login_attempts=row.failed_login_attempts,
        locked_until=row.locked_until,
        preferences=row.preferences,
        avatar_storage_key=row.avatar_storage_key,
        version=row.version,
    )


def user_to_orm(entity: User, row: UserOrmModel | None = None) -> UserOrmModel:
    row = row or UserOrmModel(id=entity.id)
    row.org_id = entity.org_id
    row.email = str(entity.email)
    row.password_hash = entity.password_hash
    row.status = entity.status.value
    row.display_name = entity.display_name
    row.mfa_enabled = entity.mfa_enabled
    row.failed_login_attempts = entity.failed_login_attempts
    row.locked_until = entity.locked_until
    row.preferences = entity.preferences
    row.avatar_storage_key = entity.avatar_storage_key
    row.version = entity.version
    return row


def session_to_domain(row: SessionOrmModel) -> Session:
    return Session(
        id=EntityId(row.id),
        user_id=EntityId(row.user_id),
        refresh_token_hash=row.refresh_token_hash,
        device_info=row.device_info,
        ip_address=row.ip_address,
        remember_me=row.remember_me,
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


def session_to_orm(entity: Session, row: SessionOrmModel | None = None) -> SessionOrmModel:
    row = row or SessionOrmModel(id=entity.id, created_at=entity.created_at)
    row.user_id = entity.user_id
    row.refresh_token_hash = entity.refresh_token_hash
    row.device_info = entity.device_info
    row.ip_address = entity.ip_address
    row.remember_me = entity.remember_me
    row.expires_at = entity.expires_at
    row.revoked_at = entity.revoked_at
    return row


def mfa_factor_to_domain(row: MfaFactorOrmModel) -> MfaFactor:
    return MfaFactor(
        id=EntityId(row.id),
        user_id=EntityId(row.user_id),
        factor_type=MfaFactorType(row.factor_type),
        secret_encrypted=row.secret_encrypted,
        recovery_code_hash=row.recovery_code_hash,
        verified_at=row.verified_at,
        consumed_at=row.consumed_at,
        created_at=row.created_at,
    )


def mfa_factor_to_orm(entity: MfaFactor, row: MfaFactorOrmModel | None = None) -> MfaFactorOrmModel:
    row = row or MfaFactorOrmModel(id=entity.id, created_at=entity.created_at)
    row.user_id = entity.user_id
    row.factor_type = entity.factor_type.value
    row.secret_encrypted = entity.secret_encrypted
    row.recovery_code_hash = entity.recovery_code_hash
    row.verified_at = entity.verified_at
    row.consumed_at = entity.consumed_at
    return row


def email_verification_token_to_domain(row: EmailVerificationTokenOrmModel) -> EmailVerificationToken:
    return EmailVerificationToken(
        id=EntityId(row.id),
        user_id=EntityId(row.user_id),
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
    )


def email_verification_token_to_orm(
    entity: EmailVerificationToken, row: EmailVerificationTokenOrmModel | None = None
) -> EmailVerificationTokenOrmModel:
    row = row or EmailVerificationTokenOrmModel(id=entity.id, user_id=entity.user_id, token_hash=entity.token_hash)
    row.expires_at = entity.expires_at
    row.consumed_at = entity.consumed_at
    return row


def password_reset_token_to_domain(row: PasswordResetTokenOrmModel) -> PasswordResetToken:
    return PasswordResetToken(
        id=EntityId(row.id),
        user_id=EntityId(row.user_id),
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
    )


def password_reset_token_to_orm(
    entity: PasswordResetToken, row: PasswordResetTokenOrmModel | None = None
) -> PasswordResetTokenOrmModel:
    row = row or PasswordResetTokenOrmModel(id=entity.id, user_id=entity.user_id, token_hash=entity.token_hash)
    row.expires_at = entity.expires_at
    row.consumed_at = entity.consumed_at
    return row


def password_history_to_domain(row: PasswordHistoryOrmModel) -> PasswordHistoryEntry:
    return PasswordHistoryEntry(
        id=EntityId(row.id), user_id=EntityId(row.user_id), password_hash=row.password_hash, created_at=row.created_at
    )


def password_history_to_orm(entity: PasswordHistoryEntry) -> PasswordHistoryOrmModel:
    return PasswordHistoryOrmModel(id=entity.id, user_id=entity.user_id, password_hash=entity.password_hash)


def organization_to_domain(row: OrganizationOrmModel) -> Organization:
    return Organization(
        id=EntityId(row.id),
        name=row.name,
        slug=row.slug,
        owner_user_id=UserId(row.owner_user_id),
        status=OrganizationStatus(row.status),
        settings=row.settings,
        description=row.description,
        logo_url=row.logo_url,
        version=row.version,
    )


def organization_to_orm(entity: Organization, row: OrganizationOrmModel | None = None) -> OrganizationOrmModel:
    row = row or OrganizationOrmModel(id=entity.id)
    row.name = entity.name
    row.slug = entity.slug
    row.owner_user_id = entity.owner_user_id
    row.status = entity.status.value
    row.settings = entity.settings
    row.description = entity.description
    row.logo_url = entity.logo_url
    row.version = entity.version
    return row


def organization_invitation_to_domain(row: OrganizationInvitationOrmModel) -> OrganizationInvitation:
    return OrganizationInvitation(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        email=Email(row.email),
        role_id=EntityId(row.role_id),
        invited_by_user_id=UserId(row.invited_by_user_id),
        token_hash=row.token_hash,
        status=InvitationStatus(row.status),
        created_at=row.created_at,
        expires_at=row.expires_at,
        accepted_at=row.accepted_at,
        revoked_at=row.revoked_at,
    )


def organization_invitation_to_orm(
    entity: OrganizationInvitation, row: OrganizationInvitationOrmModel | None = None
) -> OrganizationInvitationOrmModel:
    row = row or OrganizationInvitationOrmModel(
        id=entity.id,
        org_id=entity.org_id,
        email=str(entity.email),
        role_id=entity.role_id,
        invited_by_user_id=entity.invited_by_user_id,
        token_hash=entity.token_hash,
        created_at=entity.created_at,
    )
    row.status = entity.status.value
    row.expires_at = entity.expires_at
    row.accepted_at = entity.accepted_at
    row.revoked_at = entity.revoked_at
    return row


def team_to_domain(row: TeamOrmModel) -> Team:
    return Team(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        name=row.name,
        description=row.description,
        parent_team_id=EntityId(row.parent_team_id) if row.parent_team_id else None,
        is_deleted=row.is_deleted,
        version=row.version,
    )


def team_to_orm(entity: Team, row: TeamOrmModel | None = None) -> TeamOrmModel:
    row = row or TeamOrmModel(id=entity.id, org_id=entity.org_id)
    row.name = entity.name
    row.description = entity.description
    row.parent_team_id = entity.parent_team_id
    row.is_deleted = entity.is_deleted
    row.version = entity.version
    return row


def team_membership_to_domain(row: TeamMembershipOrmModel) -> TeamMembership:
    return TeamMembership(
        id=EntityId(row.id),
        team_id=EntityId(row.team_id),
        user_id=UserId(row.user_id),
        team_role=TeamRole(row.team_role),
        joined_at=row.joined_at,
    )


def team_membership_to_orm(entity: TeamMembership) -> TeamMembershipOrmModel:
    return TeamMembershipOrmModel(
        id=entity.id, team_id=entity.team_id, user_id=entity.user_id, team_role=entity.team_role.value
    )


def role_to_domain(row: RoleOrmModel, permission_ids: set[EntityId] | None = None) -> Role:
    role = Role(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id) if row.org_id else None,
        name=row.name,
        description=row.description,
        is_system_role=row.is_system_role,
        parent_role_id=EntityId(row.parent_role_id) if row.parent_role_id else None,
        version=row.version,
    )
    role.permission_ids = permission_ids or set()
    return role


def role_to_orm(entity: Role, row: RoleOrmModel | None = None) -> RoleOrmModel:
    row = row or RoleOrmModel(id=entity.id, org_id=entity.org_id, is_system_role=entity.is_system_role)
    row.name = entity.name
    row.description = entity.description
    row.parent_role_id = entity.parent_role_id
    row.version = entity.version
    return row


def permission_to_domain(row: PermissionOrmModel) -> Permission:
    return Permission(id=EntityId(row.id), resource=row.resource, action=row.action, description=row.description)


def permission_to_orm(entity: Permission) -> PermissionOrmModel:
    return PermissionOrmModel(
        id=entity.id, resource=entity.resource, action=entity.action, description=entity.description
    )


def user_role_assignment_to_domain(row: UserRoleOrmModel) -> UserRoleAssignment:
    return UserRoleAssignment(
        id=EntityId(row.id), user_id=UserId(row.user_id), role_id=EntityId(row.role_id), org_id=OrgId(row.org_id)
    )


def user_role_assignment_to_orm(entity: UserRoleAssignment) -> UserRoleOrmModel:
    return UserRoleOrmModel(id=entity.id, user_id=entity.user_id, role_id=entity.role_id, org_id=entity.org_id)


def trusted_device_to_domain(row: TrustedDeviceOrmModel) -> TrustedDevice:
    return TrustedDevice(
        id=EntityId(row.id),
        user_id=UserId(row.user_id),
        device_fingerprint_hash=row.device_fingerprint_hash,
        label=row.label,
        trusted_until=row.trusted_until,
        created_at=row.created_at,
    )


def trusted_device_to_orm(entity: TrustedDevice) -> TrustedDeviceOrmModel:
    return TrustedDeviceOrmModel(
        id=entity.id,
        user_id=entity.user_id,
        device_fingerprint_hash=entity.device_fingerprint_hash,
        label=entity.label,
        trusted_until=entity.trusted_until,
    )


def audit_log_to_domain(row: AuditLogOrmModel) -> AuditLogRecord:
    return AuditLogRecord(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        category=AuditEventCategory(row.category),
        action=row.action,
        actor_user_id=UserId(row.actor_user_id) if row.actor_user_id else None,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        ip_address=row.ip_address,
        metadata=row.metadata_,
        occurred_at=row.occurred_at,
    )


def audit_log_to_orm(entity: AuditLogRecord) -> AuditLogOrmModel:
    return AuditLogOrmModel(
        id=entity.id,
        org_id=entity.org_id,
        category=entity.category.value,
        action=entity.action,
        actor_user_id=entity.actor_user_id,
        resource_type=entity.resource_type,
        resource_id=entity.resource_id,
        ip_address=entity.ip_address,
        metadata_=entity.metadata,
        occurred_at=entity.occurred_at,
    )
