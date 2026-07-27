"""
Domain-event-to-integration-event mapping helpers. Contexts that publish
across the bus define a small mapper implementing this Protocol rather than
letting IntegrationEvent construction leak into command handlers.
"""

from __future__ import annotations

from typing import Protocol

from app.platform_core.events.contracts import DomainEvent, IntegrationEvent


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
