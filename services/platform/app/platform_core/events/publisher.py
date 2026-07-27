"""
Event Publisher: writes IntegrationEvents to the outbox table within the
same database transaction as the state change that produced them (Outbox
Pattern, ADR-014). A separate outbox-relay background job (see
platform_core.jobs) reads unpublished rows and forwards them to the
RabbitMQ Event Bus — this class never talks to RabbitMQ directly, which is
what makes the write atomic with the business transaction.
"""

from __future__ import annotations

from typing import Protocol

from app.platform_core.events.contracts import IntegrationEvent


class OutboxWriter(Protocol):
    """Implemented in each bounded context's infrastructure layer, backed
    by that context's `<schema>.outbox_messages` table, and given the same
    DB session/transaction as the caller."""

    async def append(self, event: IntegrationEvent) -> None: ...


class EventPublisher:
    def __init__(self, outbox: OutboxWriter) -> None:
        self._outbox = outbox

    async def publish(self, event: IntegrationEvent) -> None:
        await self._outbox.append(event)

    async def publish_all(self, events: list[IntegrationEvent]) -> None:
        for event in events:
            await self._outbox.append(event)
