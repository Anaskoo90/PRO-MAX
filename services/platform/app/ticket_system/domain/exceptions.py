"""Ticket System domain exceptions, layered on platform_core's exception
hierarchy exactly like every prior context's do."""

from __future__ import annotations

from app.platform_core.errors.domain_exceptions import (
    BusinessRuleViolationError,
    EntityNotFoundError,
)
from app.platform_core.shared_kernel.error_codes import ErrorCode


class TicketNotFoundError(EntityNotFoundError):
    def __init__(self, ticket_id: object) -> None:
        super().__init__("Ticket", ticket_id)


class InsufficientTicketPermissionError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, action: str) -> None:
        super().__init__("insufficient_ticket_permission", f"Missing permission 'ticket:{action}'")


class InvalidTicketTransitionError(BusinessRuleViolationError):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            "invalid_ticket_transition", f"Cannot transition ticket from '{current_status}' to '{target_status}'"
        )


class TicketCategoryNotFoundError(EntityNotFoundError):
    def __init__(self, category_id: object) -> None:
        super().__init__("TicketCategory", category_id)


class TicketOrganizationNotActiveError(BusinessRuleViolationError):
    """The organization behind the Discord guild is suspended or deactivated,
    so no ticket operation may run for it (HTTP 403, ORGANIZATION_NOT_ACTIVE)."""

    code = ErrorCode.ORGANIZATION_NOT_ACTIVE

    def __init__(self) -> None:
        super().__init__(
            "ticket_organization_not_active",
            "The organization linked to this server is suspended or deactivated",
        )


class GuildNotLinkedForTicketsError(BusinessRuleViolationError):
    def __init__(self, discord_guild_id: str) -> None:
        super().__init__(
            "guild_not_linked_for_tickets",
            f"Discord guild '{discord_guild_id}' is not linked to a GuildDesk organization",
        )


class ClosedTicketMessageError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__(
            "closed_ticket_message",
            "Messages cannot be added to a closed ticket",
        )


class DiscordMessageConflictError(BusinessRuleViolationError):
    def __init__(self, discord_message_id: str) -> None:
        super().__init__(
            "discord_message_conflict",
            f"Discord message '{discord_message_id}' is already attached to another ticket",
        )


class TicketAttachmentNotFoundError(EntityNotFoundError):
    def __init__(self, attachment_id: object) -> None:
        super().__init__("TicketAttachment", attachment_id)


class InvalidTicketAttachmentError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_ticket_attachment", reason)


class ClosedTicketAttachmentError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__(
            "closed_ticket_attachment",
            "Attachments cannot be added to a closed ticket",
        )
