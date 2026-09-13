"""aio-pika implementation of the platform MessageBus contract."""

from __future__ import annotations

import asyncio

import aio_pika
from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractRobustChannel,
    AbstractRobustConnection,
    AbstractRobustExchange,
)

from app.platform_core.errors.infrastructure_exceptions import MessagePublishError
from app.platform_core.messaging.bus import RawMessageHandler


class RabbitMqMessageBus:
    def __init__(
        self,
        *,
        url: str,
        exchange_name: str = "guilddesk.events",
        connection_timeout_seconds: float = 10.0,
    ) -> None:
        self._url = url
        self._exchange_name = exchange_name
        self._connection_timeout_seconds = connection_timeout_seconds
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._exchange: AbstractRobustExchange | None = None
        self._connect_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return bool(
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
        )

    async def connect(self) -> None:
        if self.is_connected:
            return
        async with self._connect_lock:
            if self.is_connected:
                return
            self._connection = await aio_pika.connect_robust(
                self._url,
                timeout=self._connection_timeout_seconds,
            )
            self._channel = await self._connection.channel(publisher_confirms=True)
            self._exchange = await self._channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )

    async def publish(
        self,
        *,
        exchange: str,
        routing_key: str,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        try:
            await self.connect()
            assert self._channel is not None
            target = self._exchange
            if exchange != self._exchange_name:
                target = await self._channel.declare_exchange(
                    exchange,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
            assert target is not None
            await target.publish(
                aio_pika.Message(
                    body=body,
                    headers=headers,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=headers.get("message_id"),
                    type=headers.get("event_type"),
                ),
                routing_key=routing_key,
            )
        except MessagePublishError:
            raise
        except Exception as exc:
            raise MessagePublishError(
                f"RabbitMQ publish failed for routing key '{routing_key}'"
            ) from exc

    async def subscribe(
        self,
        *,
        queue: str,
        routing_keys: list[str],
        handler: RawMessageHandler,
    ) -> None:
        await self.connect()
        assert self._channel is not None
        assert self._exchange is not None
        declared_queue = await self._channel.declare_queue(queue, durable=True)
        for routing_key in routing_keys:
            await declared_queue.bind(self._exchange, routing_key=routing_key)

        async def _consume(message: AbstractIncomingMessage) -> None:
            async with message.process(requeue=True):
                headers = {
                    str(key): str(value)
                    for key, value in (message.headers or {}).items()
                }
                await handler(message.body, headers)

        await declared_queue.consume(_consume)

    async def close(self) -> None:
        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._exchange = None
        self._channel = None
        self._connection = None
