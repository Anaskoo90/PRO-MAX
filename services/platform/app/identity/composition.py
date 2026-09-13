"""
Identity composition root: wires domain/application/infrastructure/
presentation together and exposes the hooks app/main.py needs — `register`
(DI container + service construction), `mount` (FastAPI routers +
dependency overrides), and `seed` (permission catalog + system roles,
called once at startup).

Follows platform_core.di.registration.ModuleRegistration so the future
composition roots for other bounded contexts (CRM, Ticketing, ...) look
identical from app/main.py's point of view.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.application.authentication import (
    AuthenticationService,
    AuthPolicy,
    OAuth2LoginService,
)
from app.identity.application.email_verification import EmailVerificationService
from app.identity.application.mfa import MfaService
from app.identity.application.organization_invitations import OrganizationInvitationService
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.application.password_management import PasswordManagementService
from app.identity.application.rbac_engine import (
    PermissionEvaluator,
    PolicyEvaluator,
    RoleResolutionService,
)
from app.identity.application.rbac_management import PermissionCatalogService, RoleService
from app.identity.application.security import (
    AuditLogQueryService,
    BruteForceGuard,
    BruteForcePolicy,
    DeviceTrustService,
    IpRestrictionChecker,
    RedisRateLimitStore,
    SecurityService,
    SuspiciousLoginDetector,
    SuspiciousLoginNotifier,
)
from app.identity.application.team_management import TeamService
from app.identity.application.user_management import UserManagementService
from app.identity.domain.events import SuspiciousLoginDetected, UserRegistered
from app.identity.infrastructure.oauth2_client import OAuth2Client, OAuth2ProviderConfig
from app.identity.infrastructure.seed_data import seed_identity
from app.identity.infrastructure.unit_of_work import IdentityUnitOfWork
from app.identity.presentation import (
    auth_router,
    deps,
    email_verification_router,
    invitations_router,
    mfa_router,
    organizations_router,
    password_router,
    rbac_router,
    security_router,
    teams_router,
    users_router,
)
from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.di.container import ServiceContainer
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger, AuditRecordSink
from app.platform_core.logging.logger import get_logger
from app.platform_core.messaging.idempotency import RedisIdempotencyStore
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.notifications.email_provider import SmtpEmailProvider
from app.platform_core.security.encryption import FieldEncryptionService
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.token import JwtTokenService
from app.platform_core.storage.local_provider import LocalFileStorageProvider

_logger = get_logger("identity.composition")


class _LoggingAuditRecordSink(AuditRecordSink):
    """Used only for platform_core-level cross-cutting audit calls
    (AuthenticationService's `audit_logger.record(...)` for login/logout) —
    the durable, queryable audit trail requested by the Audit Logs
    submodule is uow.audit_logs (SqlAlchemyAuditLogRepository), written
    directly by the services that own each category. This sink remains a
    secondary, log-only record of the same events."""

    async def write(self, record) -> None:  # noqa: ANN001
        await _logger.ainfo(
            "audit_record",
            org_id=str(record.org_id),
            actor_id=str(record.actor_id) if record.actor_id else None,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            metadata=record.metadata,
        )


class IdentityModule:
    module_name = "identity"

    def __init__(self, settings: PlatformSettings) -> None:
        self._settings = settings
        engine = create_async_engine(str(settings.database_url))
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        self.redis_client = Redis.from_url(str(settings.redis_url), decode_responses=True)

        self.dispatcher = EventDispatcher()
        self.password_hasher = PasswordHashingService()
        self.token_service = JwtTokenService(signing_key=settings.jwt_signing_key)
        token_hash_pepper = settings.token_hash_pepper.get_secret_value()
        self.encryption = FieldEncryptionService(
            settings.field_encryption_key.get_secret_value().encode()
        )
        self.audit_logger = AuditLogger(_LoggingAuditRecordSink())
        email_provider = None
        if settings.smtp_host:
            email_provider = SmtpEmailProvider(
                host=settings.smtp_host,
                port=settings.smtp_port,
                from_address=settings.smtp_from_address,
                from_name=settings.smtp_from_name,
                username=settings.smtp_username,
                password=(
                    settings.smtp_password.get_secret_value()
                    if settings.smtp_password is not None
                    else None
                ),
                use_ssl=settings.smtp_use_ssl,
                start_tls=settings.smtp_start_tls,
                timeout_seconds=settings.smtp_timeout_seconds,
            )
        self.notification_dispatcher = NotificationDispatcher(email_provider=email_provider)
        self.file_storage = LocalFileStorageProvider(Path("./.local-storage/avatars"))

        web_app_base_url = str(settings.web_app_base_url).rstrip("/")

        def uow_factory() -> IdentityUnitOfWork:
            return IdentityUnitOfWork(self._session_factory)

        self._uow_factory = uow_factory

        # --- RBAC Engine ---
        self.role_resolution_service = RoleResolutionService(uow_factory=uow_factory)
        self.permission_evaluator = PermissionEvaluator(uow_factory=uow_factory, role_resolution=self.role_resolution_service)
        self.policy_evaluator = PolicyEvaluator(permission_evaluator=self.permission_evaluator)
        self.permission_catalog_service = PermissionCatalogService(uow_factory=uow_factory)
        self.role_service = RoleService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_catalog=self.permission_catalog_service
        )

        # --- Security submodule ---
        rate_limit_store = RedisRateLimitStore(self.redis_client)
        self.security_service = SecurityService(
            brute_force_guard=BruteForceGuard(store=rate_limit_store),
            ip_restriction_checker=IpRestrictionChecker(),
            device_trust_service=DeviceTrustService(uow_factory=uow_factory),
            suspicious_login_detector=SuspiciousLoginDetector(uow_factory=uow_factory),
            uow_factory=uow_factory,
        )
        self.audit_log_query_service = AuditLogQueryService(uow_factory=uow_factory)
        self._suspicious_login_notifier = SuspiciousLoginNotifier(
            uow_factory=uow_factory, notification_dispatcher=self.notification_dispatcher
        )

        # --- Authentication (now security-aware) ---
        self.authentication_service = AuthenticationService(
            uow_factory=uow_factory,
            password_hasher=self.password_hasher,
            token_service=self.token_service,
            dispatcher=self.dispatcher,
            audit_logger=self.audit_logger,
            security_service=self.security_service,
            policy=AuthPolicy(refresh_token_pepper=token_hash_pepper),
        )
        oauth2_clients = {}
        if (
            settings.oauth_discord_client_id
            and settings.oauth_discord_client_secret
            and settings.oauth_discord_redirect_uri
        ):
            oauth2_clients["discord"] = OAuth2Client(
                OAuth2ProviderConfig(
                    provider_key="discord",
                    client_id=settings.oauth_discord_client_id,
                    client_secret=settings.oauth_discord_client_secret.get_secret_value(),
                    authorization_endpoint="https://discord.com/oauth2/authorize",
                    token_endpoint="https://discord.com/api/oauth2/token",
                    userinfo_endpoint="https://discord.com/api/users/@me",
                    redirect_uri=str(settings.oauth_discord_redirect_uri),
                    scopes=("identify", "email"),
                )
            )
        self.oauth2_login_service = OAuth2LoginService(
            uow_factory=uow_factory,
            oauth2_clients=oauth2_clients,
            authentication_service=self.authentication_service,
            token_service=self.token_service,
            state_replay_store=RedisIdempotencyStore(self.redis_client),
        )
        self.user_management_service = UserManagementService(
            uow_factory=uow_factory,
            password_hasher=self.password_hasher,
            dispatcher=self.dispatcher,
            audit_logger=self.audit_logger,
            file_storage=self.file_storage,
        )
        self.email_verification_service = EmailVerificationService(
            uow_factory=uow_factory,
            notification_dispatcher=self.notification_dispatcher,
            dispatcher=self.dispatcher,
            token_pepper=token_hash_pepper,
            verification_link_base_url=f"{web_app_base_url}/verify-email",
        )
        self.password_management_service = PasswordManagementService(
            uow_factory=uow_factory,
            password_hasher=self.password_hasher,
            notification_dispatcher=self.notification_dispatcher,
            dispatcher=self.dispatcher,
            token_pepper=token_hash_pepper,
            reset_link_base_url=f"{web_app_base_url}/reset-password",
        )
        self.mfa_service = MfaService(
            uow_factory=uow_factory,
            encryption=self.encryption,
            dispatcher=self.dispatcher,
            authentication_service=self.authentication_service,
            recovery_code_pepper=token_hash_pepper,
            token_service=self.token_service,
            challenge_replay_store=RedisIdempotencyStore(self.redis_client),
            attempt_guard=BruteForceGuard(
                store=rate_limit_store,
                policy=BruteForcePolicy(max_attempts_per_window=10, window_seconds=300),
            ),
        )
        self.organization_management_service = OrganizationManagementService(
            uow_factory=uow_factory, password_hasher=self.password_hasher, dispatcher=self.dispatcher,
        )
        self.organization_invitation_service = OrganizationInvitationService(
            uow_factory=uow_factory,
            password_hasher=self.password_hasher,
            notification_dispatcher=self.notification_dispatcher,
            dispatcher=self.dispatcher,
            token_pepper=token_hash_pepper,
            invitation_link_base_url=f"{web_app_base_url}/accept-invitation",
        )
        self.team_service = TeamService(uow_factory=uow_factory, dispatcher=self.dispatcher)

        # Event-driven wiring — every subscription decouples one submodule
        # from another; none of the publishers below import their subscriber.
        self.dispatcher.subscribe(UserRegistered, self.email_verification_service.on_user_registered)
        self.dispatcher.subscribe(SuspiciousLoginDetected, self._suspicious_login_notifier.on_suspicious_login_detected)

    def create_unit_of_work(self) -> IdentityUnitOfWork:
        """Public seam for other bounded contexts' composition roots to
        build an Anti-Corruption Layer against (e.g.
        app.projects.infrastructure.identity_adapter) — the same
        session_factory this module uses internally, exposed deliberately
        rather than accessed via the private `_uow_factory` closure."""
        return self._uow_factory()

    async def shutdown(self) -> None:
        await self.redis_client.aclose()

    async def seed(self, *, extra_permissions: tuple = ()) -> None:
        """Idempotent — safe to call on every startup. Populates the
        Permission Catalog and system roles (org_owner/org_admin/member).
        `extra_permissions` lets other bounded contexts (Projects &
        Workspaces, ...) register their own resource:action pairs into
        this same table without Identity importing their code."""
        async with self._uow_factory() as uow:
            await seed_identity(uow, extra_permissions=extra_permissions)
        await _logger.ainfo("identity_seed_complete", extra_permission_count=len(extra_permissions))

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(AuthenticationService, self.authentication_service)
        container.register_instance(OAuth2LoginService, self.oauth2_login_service)
        container.register_instance(UserManagementService, self.user_management_service)
        container.register_instance(EmailVerificationService, self.email_verification_service)
        container.register_instance(PasswordManagementService, self.password_management_service)
        container.register_instance(MfaService, self.mfa_service)
        container.register_instance(JwtTokenService, self.token_service)
        container.register_instance(OrganizationManagementService, self.organization_management_service)
        container.register_instance(OrganizationInvitationService, self.organization_invitation_service)
        container.register_instance(TeamService, self.team_service)
        container.register_instance(RoleService, self.role_service)
        container.register_instance(PermissionCatalogService, self.permission_catalog_service)
        container.register_instance(PermissionEvaluator, self.permission_evaluator)
        container.register_instance(PolicyEvaluator, self.policy_evaluator)
        container.register_instance(SecurityService, self.security_service)
        container.register_instance(AuditLogQueryService, self.audit_log_query_service)

    def mount(self, app: FastAPI) -> None:
        app.include_router(auth_router.router)
        app.include_router(users_router.router)
        app.include_router(email_verification_router.router)
        app.include_router(password_router.router)
        app.include_router(mfa_router.router)
        app.include_router(organizations_router.router)
        app.include_router(invitations_router.router)
        app.include_router(teams_router.router)
        app.include_router(rbac_router.router)
        app.include_router(security_router.router)

        app.dependency_overrides[deps.get_token_service] = lambda: self.token_service
        app.dependency_overrides[deps.get_authentication_service] = lambda: self.authentication_service
        app.dependency_overrides[deps.get_oauth2_login_service] = lambda: self.oauth2_login_service
        app.dependency_overrides[deps.get_user_management_service] = lambda: self.user_management_service
        app.dependency_overrides[deps.get_email_verification_service] = lambda: self.email_verification_service
        app.dependency_overrides[deps.get_password_management_service] = lambda: self.password_management_service
        app.dependency_overrides[deps.get_mfa_service] = lambda: self.mfa_service
        app.dependency_overrides[deps.get_organization_management_service] = lambda: self.organization_management_service
        app.dependency_overrides[deps.get_organization_invitation_service] = lambda: self.organization_invitation_service
        app.dependency_overrides[deps.get_team_service] = lambda: self.team_service
        app.dependency_overrides[deps.get_role_service] = lambda: self.role_service
        app.dependency_overrides[deps.get_permission_catalog_service] = lambda: self.permission_catalog_service
        app.dependency_overrides[deps.get_permission_evaluator] = lambda: self.permission_evaluator
        app.dependency_overrides[deps.get_security_service] = lambda: self.security_service
        app.dependency_overrides[deps.get_audit_log_query_service] = lambda: self.audit_log_query_service
