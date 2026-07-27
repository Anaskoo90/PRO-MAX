"""Aggregate-root mixin for recording domain events prior to dispatch."""

from __future__ import annotations

from app.platform_core.events.contracts import DomainEvent


class EventRecordingMixin:
    """Mixed into aggregate roots (satisfies shared_kernel.interfaces.AggregateRoot's
    pull_domain_events contract). Events are recorded during command handling and
    pulled + dispatched by the application layer after a successful commit —
    never dispatched from inside the aggregate itself, which stays free of any
    dispatcher dependency."""

    def __init__(self) -> None:
        self._domain_events: list[DomainEvent] = []

    def record_event(self, event: DomainEvent) -> None:
        self._domain_events.append(event)

    def pull_domain_events(self) -> list[DomainEvent]:
        events, self._domain_events = self._domain_events, []
        return events
