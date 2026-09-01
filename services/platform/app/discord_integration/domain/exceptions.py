"""Discord Integration domain exceptions, layered on platform_core's
exception hierarchy exactly like every prior context's do."""

from __future__ import annotations

from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError, EntityNotFoundError
from app.platform_core.shared_kernel.error_codes import ErrorCode


class InvalidSetupCodeError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("invalid_setup_code", "This setup code is invalid")


class SetupCodeExpiredError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("setup_code_expired", "This setup code has expired")


class SetupCodeAlreadyUsedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("setup_code_already_used", "This setup code was already used")


class GuildLinkNotFoundError(EntityNotFoundError):
    def __init__(self, guild_link_id: object) -> None:
        super().__init__("GuildLink", guild_link_id)


class GuildNotLinkedError(BusinessRuleViolationError):
    def __init__(self, discord_guild_id: str) -> None:
        super().__init__(
            "guild_not_linked", f"Discord guild '{discord_guild_id}' is not linked to any organization"
        )


class GuildAlreadyLinkedToAnotherOrganizationError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__(
            "guild_already_linked_to_another_organization",
            "This Discord server is already linked to a different organization; unlink it there first",
        )


class InsufficientDiscordPermissionError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self) -> None:
        super().__init__(
            "insufficient_discord_permission", "This action requires the 'discord:manage_integration' permission"
        )
