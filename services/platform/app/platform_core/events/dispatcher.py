"""
Event Dispatcher: in-process pub/sub for DomainEvent subclasses, used
within a single bounded context (e.g. TaskCompleted triggers a same-context
projection update) without going through the message broker.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Awaitable, Callable, TypeVar

from app.platform_core.events.contracts import DomainEvent
from app.platform_core.logging.logger import get_logger

TEvent = TypeVar("TEvent", bound=DomainEvent)
Handler = Callable[[TEvent], Awaitable[None]]

_logger = get_logger("events.dispatcher")


class EventDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[TEvent], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def dispatch(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                await _logger.aerror(
                    "domain_event_handler_failed",
                    event_type=type(event).__name__,
                    handler=getattr(handler, "__qualname__", repr(handler)),
                    exc_info=True,
                )
                raise

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        for event in events:
            await self.dispatch(event)
