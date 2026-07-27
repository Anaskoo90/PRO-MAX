"""
Event Subscribers: registry mapping a wire event_type string to the
in-process handler(s) that consume it once the Messaging Foundation's
consumer delivers it off the queue. Kept separate from EventDispatcher
(domain events) since subscribers here are registered per-process at
startup and keyed by the wire contract name, not the Python type.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Awaitable, Callable

from app.platform_core.events.contracts import IntegrationEvent
from app.platform_core.logging.logger import get_logger

IntegrationEventHandler = Callable[[IntegrationEvent], Awaitable[None]]

_logger = get_logger("events.subscriber")


class SubscriberRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[IntegrationEventHandler]] = defaultdict(list)

    def on(self, event_type: str, handler: IntegrationEventHandler) -> None:
        self._handlers[event_type].append(handler)

    def handlers_for(self, event_type: str) -> list[IntegrationEventHandler]:
        return self._handlers.get(event_type, [])

    async def deliver(self, event_type: str, event: IntegrationEvent) -> None:
        handlers = self.handlers_for(event_type)
        if not handlers:
            await _logger.awarn("integration_event_no_subscribers", event_type=event_type)
            return
        for handler in handlers:
            await handler(event)
