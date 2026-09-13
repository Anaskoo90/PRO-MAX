"""Lifecycle composition for RabbitMQ and the recurring outbox relay."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine

from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.jobs.scheduler import JobDefinition, JobScheduler
from app.platform_core.messaging.outbox_relay import SqlAlchemyOutboxRelay
from app.platform_core.messaging.rabbitmq_bus import RabbitMqMessageBus
from app.platform_core.observability.health import (
    DependencyCheckResult,
    HealthStatus,
)


class MessagingRuntime:
    def __init__(self, settings: PlatformSettings) -> None:
        self.message_bus = RabbitMqMessageBus(
            url=settings.rabbitmq_url,
            exchange_name=settings.rabbitmq_exchange,
            connection_timeout_seconds=settings.rabbitmq_connection_timeout_seconds,
        )
        self._engine = create_async_engine(str(settings.database_url))
        self.outbox_relay = SqlAlchemyOutboxRelay(
            engine=self._engine,
            message_bus=self.message_bus,
            exchange=settings.rabbitmq_exchange,
            batch_size=settings.outbox_relay_batch_size,
        )
        self._scheduler = JobScheduler()
        self._scheduler.register(
            JobDefinition(
                name="platform_outbox_relay",
                func=self.outbox_relay.run_once,
                interval_seconds=settings.outbox_relay_interval_seconds,
            )
        )

    async def start(self) -> None:
        await self.message_bus.connect()
        await self._scheduler.start()

    async def stop(self) -> None:
        await self._scheduler.stop()
        await self.message_bus.close()
        await self._engine.dispose()

    async def health_check(self) -> DependencyCheckResult:
        if self.message_bus.is_connected:
            return DependencyCheckResult(
                name="rabbitmq",
                status=HealthStatus.HEALTHY,
            )
        return DependencyCheckResult(
            name="rabbitmq",
            status=HealthStatus.UNHEALTHY,
            detail="RabbitMQ connection is not active",
        )
