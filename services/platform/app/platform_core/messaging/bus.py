"""
Message Bus Interfaces: the Protocol platform_core.events.publisher's
outbox-relay job publishes through, and platform_core.events.subscriber's
consumer loop reads from. The concrete RabbitMQ implementation lives in
infrastructure (not platform_core), built on aio-pika — nothing above this
Protocol depends on aio-pika directly.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol

RawMessageHandler = Callable[[bytes, dict[str, str]], Awaitable[None]]


class MessageBus(Protocol):
    async def publish(
        self, *, exchange: str, routing_key: str, body: bytes, headers: dict[str, str]
    ) -> None: ...

    async def subscribe(
        self, *, queue: str, routing_keys: list[str], handler: RawMessageHandler
    ) -> None: ...

    async def close(self) -> None: ...
