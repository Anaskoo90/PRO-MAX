from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.composition import IdentityModule
from app.notifications.application.notification_service import NotificationService
from app.notifications.infrastructure.delivery_recorder import (
    SqlAlchemyNotificationDeliveryRecorder,
)
from app.notifications.infrastructure.unit_of_work import NotificationsUnitOfWork
from app.notifications.presentation import deps, router
from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.di.container import ServiceContainer


class NotificationsModule:
    module_name = "notifications"

    def __init__(
        self, settings: PlatformSettings, identity_module: IdentityModule
    ) -> None:
        self._settings = settings
        self._engine = create_async_engine(str(settings.database_url))
        session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        def uow_factory() -> NotificationsUnitOfWork:
            return NotificationsUnitOfWork(session_factory)

        self._uow_factory = uow_factory
        self.notification_service = NotificationService(uow_factory=uow_factory)
        self.delivery_recorder = SqlAlchemyNotificationDeliveryRecorder(
            uow_factory=uow_factory
        )
        identity_module.notification_dispatcher.set_delivery_recorder(
            self.delivery_recorder
        )

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(NotificationService, self.notification_service)

    async def shutdown(self) -> None:
        await self._engine.dispose()

    def mount(self, app: FastAPI) -> None:
        app.include_router(router.router)
        app.dependency_overrides[deps.get_notification_service] = (
            lambda: self.notification_service
        )


__all__ = ["NotificationsModule"]
