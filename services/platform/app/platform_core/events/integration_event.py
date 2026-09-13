"""
Domain-event-to-integration-event mapping helpers. Contexts that publish
across the bus define a small mapper implementing this Protocol rather than
letting IntegrationEvent construction leak into command handlers.
"""

from __future__ import annotations

from typing import Protocol

from app.platform_core.events.contracts import DomainEvent, IntegrationEvent
from app.platform_core.events.publisher import OutboxWriter
from app.platform_core.shared_kernel.types import OrgId


class IntegrationEventMapper(Protocol):
    def can_map(self, event: DomainEvent) -> bool: ...

    def to_integration_event(self, event: DomainEvent) -> IntegrationEvent: ...


class IntegrationEventMapperRegistry:
    def __init__(self) -> None:
        self._mappers: list[IntegrationEventMapper] = []

    def register(self, mapper: IntegrationEventMapper) -> None:
        self._mappers.append(mapper)

    def map_all(self, domain_events: list[DomainEvent]) -> list[IntegrationEvent]:
        mapped: list[IntegrationEvent] = []
        for event in domain_events:
            for mapper in self._mappers:
                if mapper.can_map(event):
                    mapped.append(mapper.to_integration_event(event))
                    break
        return mapped


def domain_event_to_integration_event(
    event: DomainEvent,
    *,
    org_id: OrgId,
) -> IntegrationEvent:
    """Create the stable wire envelope for a context-owned domain event."""

    return IntegrationEvent(
        event_id=event.event_id,
        occurred_at=event.occurred_at,
        org_id=org_id,
        payload={
            "event_type": event.event_type,
            "data": event.model_dump(mode="json"),
        },
    )


async def append_domain_events_to_outbox(
    outbox: OutboxWriter,
    events: list[DomainEvent],
    *,
    org_id: OrgId,
) -> None:
    """Persist mapped events before the owning business transaction commits."""

    for event in events:
        await outbox.append(
            domain_event_to_integration_event(event, org_id=org_id)
        )
