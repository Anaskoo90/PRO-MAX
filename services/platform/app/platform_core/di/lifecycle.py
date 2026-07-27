"""
Lifecycle Management: application-scoped async resources (DB engine, Redis
pool, RabbitMQ connection) that must be opened once at startup and closed
once at shutdown, tied to the FastAPI lifespan context.

Usage (composition root):

    @asynccontextmanager
    async def db_engine():
        engine = create_async_engine(settings.database_url)
        try:
            yield engine
        finally:
            await engine.dispose()

    lifecycle.register(db_engine)
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Callable


class LifecycleManager:
    """Registers async context-manager factories and guarantees teardown in
    reverse-registration order, even if a later startup step fails."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._factories: list[Callable[[], AbstractAsyncContextManager]] = []

    def register(self, resource_cm_factory: Callable[[], AbstractAsyncContextManager]) -> None:
        self._factories.append(resource_cm_factory)

    async def startup(self) -> None:
        for factory in self._factories:
            await self._stack.enter_async_context(factory())

    async def shutdown(self) -> None:
        await self._stack.aclose()
