"""
Discord Setup submodule: the setup-token exchange that binds a Discord
guild to a GuildDesk organization, plus guild-link listing/unlink.

Token lifecycle (expired / already-used / invalid) is intentionally NOT
enforced on the entity itself, matching every other token-based flow in
this platform (EmailVerificationToken/PasswordResetToken/
OrganizationInvitation): this service checks expires_at/consumed_at before
calling GuildSetupToken.consume().

complete_setup / unlink_guild_by_discord_id / get_status_by_discord_guild_id
are the bot-facing operations — no GuildDesk permission check is performed
here. Their trust boundary is the caller (presentation/bot_authentication.py's
bot-shared-secret dependency) plus, on the Discord side, the bot's own
"Manage Server" gate before it ever calls these. See the Discord Setup
Wizard design doc for why that's the deliberate v1 boundary.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from app.discord_integration.application.dtos import GuildLinkDTO, GuildLinkStatusDTO, SetupTokenDTO
from app.discord_integration.application.authorization_helpers import DiscordAuthorization
from app.discord_integration.application.ports import OrganizationLookupPort, OrgPermissionCheckerPort
from app.discord_integration.domain.audit import DiscordAuditEventCategory, DiscordAuditLogRecord
from app.discord_integration.domain.entities import GuildLink, GuildSetupToken
from app.discord_integration.domain.exceptions import (
    GuildAlreadyLinkedToAnotherOrganizationError,
    GuildLinkNotFoundError,
    GuildNotLinkedError,
    InvalidSetupCodeError,
    SetupCodeAlreadyUsedError,
    SetupCodeExpiredError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.security.hashing import hash_for_lookup
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId

_TOKEN_PEPPER = "change-me-in-production"  # see platform_core.security.secrets_provider

# Crockford-style alphabet minus ambiguous characters (0/O, 1/I/L) — typed
# by hand into a Discord slash-command argument, so legibility matters more
# here than for the long token_urlsafe values used elsewhere.
_SETUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_SETUP_CODE_LENGTH = 8

# VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | READ_MESSAGE_HISTORY | USE_APPLICATION_COMMANDS
_BOT_INVITE_PERMISSIONS = (1 << 10) | (1 << 11) | (1 << 14) | (1 << 16) | (1 << 31)


def _generate_setup_code() -> str:
    return "".join(secrets.choice(_SETUP_CODE_ALPHABET) for _ in range(_SETUP_CODE_LENGTH))


def _to_guild_link_dto(link: GuildLink) -> GuildLinkDTO:
    return GuildLinkDTO(
        id=link.id, org_id=link.org_id, discord_guild_id=link.discord_guild_id,
        discord_guild_name=link.discord_guild_name, status=link.status.value,
        linked_by_user_id=link.linked_by_user_id, linked_at=link.linked_at, revoked_at=link.revoked_at,
    )


class DiscordSetupService:
    def __init__(
        self,
        *,
        uow_factory,
        dispatcher: EventDispatcher,
        permission_checker: OrgPermissionCheckerPort,
        organization_lookup: OrganizationLookupPort,
        discord_application_id: str,
        setup_token_ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = DiscordAuthorization(permission_checker=permission_checker)
        self._organization_lookup = organization_lookup
        self._discord_application_id = discord_application_id
        self._setup_token_ttl = setup_token_ttl

    def _build_invite_url(self) -> str:
        return (
            "https://discord.com/api/oauth2/authorize"
            f"?client_id={self._discord_application_id}"
            f"&scope=bot%20applications.commands"
            f"&permissions={_BOT_INVITE_PERMISSIONS}"
        )

    async def request_setup_token(self, *, org_id: OrgId, requested_by_user_id: UserId) -> SetupTokenDTO:
        await self._authorization.assert_can_manage_integration(org_id=org_id, user_id=requested_by_user_id)

        raw_code = _generate_setup_code()
        token_hash = hash_for_lookup(raw_code, secret_pepper=_TOKEN_PEPPER)

        async with self._uow_factory() as uow:
            # Superseding any outstanding request rather than allowing many
            # live codes at once — same "resend supersedes" convention as
            # OrganizationInvitationService.invite_member.
            await uow.guild_setup_tokens.invalidate_outstanding_for_org(org_id)
            token = GuildSetupToken.create(
                org_id=org_id, requested_by_user_id=requested_by_user_id, token_hash=token_hash,
                ttl=self._setup_token_ttl,
            )
            await uow.guild_setup_tokens.add(token)
            await uow.audit_logs.add(
                DiscordAuditLogRecord.create(
                    org_id=org_id, category=DiscordAuditEventCategory.GUILD_LINK_CHANGE,
                    action="guild_setup_token_requested", actor_user_id=requested_by_user_id,
                    resource_type="guild_setup_token", resource_id=str(token.id),
                )
            )
            await uow.commit()

        return SetupTokenDTO(raw_code=raw_code, invite_url=self._build_invite_url(), expires_at=token.expires_at)

    async def complete_setup(
        self, *, raw_code: str, discord_guild_id: str, discord_guild_name: str, discord_user_id: str
    ) -> GuildLinkDTO:
        token_hash = hash_for_lookup(raw_code, secret_pepper=_TOKEN_PEPPER)

        async with self._uow_factory() as uow:
            token = await uow.guild_setup_tokens.get_by_token_hash(token_hash)
            if token is None:
                raise InvalidSetupCodeError()
            if token.is_consumed():
                raise SetupCodeAlreadyUsedError()
            if token.is_expired():
                raise SetupCodeExpiredError()

            existing = await uow.guild_links.get_by_discord_guild_id(discord_guild_id)
            if existing is not None and existing.is_active() and existing.org_id != token.org_id:
                raise GuildAlreadyLinkedToAnotherOrganizationError()

            if existing is not None:
                existing.relink(
                    org_id=token.org_id, discord_guild_name=discord_guild_name,
                    linked_by_user_id=UserId(token.requested_by_user_id),
                )
                link = existing
                await uow.guild_links.update(link)
            else:
                link = GuildLink.create(
                    org_id=token.org_id, discord_guild_id=discord_guild_id, discord_guild_name=discord_guild_name,
                    linked_by_user_id=UserId(token.requested_by_user_id),
                )
                await uow.guild_links.add(link)

            token.consume(discord_guild_id=discord_guild_id)
            await uow.guild_setup_tokens.update(token)

            events = link.pull_domain_events()
            await uow.audit_logs.add(
                DiscordAuditLogRecord.create(
                    org_id=link.org_id, category=DiscordAuditEventCategory.GUILD_LINK_CHANGE,
                    action="guild_linked", actor_user_id=token.requested_by_user_id,
                    resource_type="guild_link", resource_id=str(link.id),
                    metadata={"discord_guild_id": discord_guild_id, "discord_user_id": discord_user_id},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_guild_link_dto(link)

    async def list_guild_links(self, *, org_id: OrgId, actor_user_id: UserId) -> list[GuildLinkDTO]:
        await self._authorization.assert_can_manage_integration(org_id=org_id, user_id=actor_user_id)
        async with self._uow_factory() as uow:
            links = await uow.guild_links.list_for_org(org_id)
            return [_to_guild_link_dto(link) for link in links]

    async def unlink_guild(self, *, org_id: OrgId, guild_link_id: EntityId, actor_user_id: UserId) -> None:
        await self._authorization.assert_can_manage_integration(org_id=org_id, user_id=actor_user_id)
        async with self._uow_factory() as uow:
            link = await uow.guild_links.get_by_id(guild_link_id)
            if link is None or link.org_id != org_id:
                raise GuildLinkNotFoundError(guild_link_id)

            link.revoke(revoked_by_user_id=actor_user_id)
            await uow.guild_links.update(link)
            events = link.pull_domain_events()
            await uow.audit_logs.add(
                DiscordAuditLogRecord.create(
                    org_id=org_id, category=DiscordAuditEventCategory.GUILD_LINK_CHANGE, action="guild_unlinked",
                    actor_user_id=actor_user_id, resource_type="guild_link", resource_id=str(link.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def unlink_guild_by_discord_id(self, *, discord_guild_id: str, discord_user_id: str) -> None:
        async with self._uow_factory() as uow:
            link = await uow.guild_links.get_active_by_discord_guild_id(discord_guild_id)
            if link is None:
                raise GuildNotLinkedError(discord_guild_id)

            org_id = link.org_id
            link.revoke(revoked_by_user_id=None)
            await uow.guild_links.update(link)
            events = link.pull_domain_events()
            await uow.audit_logs.add(
                DiscordAuditLogRecord.create(
                    org_id=org_id, category=DiscordAuditEventCategory.GUILD_LINK_CHANGE, action="guild_unlinked",
                    actor_user_id=None, resource_type="guild_link", resource_id=str(link.id),
                    metadata={"discord_guild_id": discord_guild_id, "discord_user_id": discord_user_id},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def resolve_org_id_by_discord_guild_id(self, *, discord_guild_id: str) -> OrgId | None:
        """Public resolution primitive for other bounded contexts' ACLs
        (Ticket System is the first consumer) — returns the org_id an
        ACTIVE GuildLink resolves to, or None if unlinked/revoked.
        GuildLinkStatusDTO is display-shaped (org name, not org id) and
        unsuitable for this; nothing about that DTO changes."""
        async with self._uow_factory() as uow:
            link = await uow.guild_links.get_active_by_discord_guild_id(discord_guild_id)
        return link.org_id if link is not None else None

    async def get_status_by_discord_guild_id(self, *, discord_guild_id: str) -> GuildLinkStatusDTO:
        async with self._uow_factory() as uow:
            link = await uow.guild_links.get_active_by_discord_guild_id(discord_guild_id)
        if link is None:
            return GuildLinkStatusDTO(linked=False)
        org_name = await self._organization_lookup.get_org_name(org_id=link.org_id)
        return GuildLinkStatusDTO(
            linked=True, org_name=org_name, discord_guild_name=link.discord_guild_name, linked_at=link.linked_at
        )
