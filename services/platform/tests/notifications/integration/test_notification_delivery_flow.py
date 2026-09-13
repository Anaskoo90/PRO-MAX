from __future__ import annotations

import os

import pytest
import pytest_asyncio
from app.notifications.application.notification_service import NotificationService
from app.notifications.infrastructure.delivery_recorder import (
    SqlAlchemyNotificationDeliveryRecorder,
)
from app.notifications.infrastructure.orm_models import (
    NotificationDeliveryAttemptOrmModel,
    NotificationOrmModel,
)
from app.notifications.infrastructure.unit_of_work import NotificationsUnitOfWork
from app.platform_core.notifications.dispatcher import (
    NotificationChannel,
    NotificationDispatcher,
    NotificationRequest,
)
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio

_TEST_DATABASE_URL = os.environ.get(
    "GUILDDESK_TEST_DATABASE_URL",
    "postgresql+asyncpg://guilddesk:guilddesk@localhost:5432/guilddesk_test",
)


class _EmailProvider:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, message) -> None:
        self.messages.append(message)


@pytest_asyncio.fixture
async def notification_context():
    engine = create_async_engine(_TEST_DATABASE_URL)
    try:
        async with engine.connect() as connection:
            outer_transaction = await connection.begin()
            session_factory = async_sessionmaker(
                connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

            def uow_factory() -> NotificationsUnitOfWork:
                return NotificationsUnitOfWork(session_factory)

            yield uow_factory, session_factory
            await outer_transaction.rollback()
    except OSError:
        pytest.skip(
            f"No reachable test database at {_TEST_DATABASE_URL}"
        )
    finally:
        await engine.dispose()


async def test_email_delivery_is_persisted_and_visible_to_its_user(
    notification_context,
) -> None:
    uow_factory, session_factory = notification_context
    provider = _EmailProvider()
    recorder = SqlAlchemyNotificationDeliveryRecorder(uow_factory=uow_factory)
    dispatcher = NotificationDispatcher(
        email_provider=provider,
        delivery_recorder=recorder,
    )
    org_id = OrgId(new_uuid7())
    user_id = UserId(new_uuid7())

    await dispatcher.dispatch(
        NotificationRequest(
            org_id=org_id,
            channel=NotificationChannel.EMAIL,
            recipient="recipient@example.com",
            recipient_user_id=user_id,
            subject="Task assigned",
            body="Open GuildDesk to view the task.",
            in_app_body="You were assigned a task.",
        )
    )

    service = NotificationService(uow_factory=uow_factory)
    page = await service.list_for_user(org_id=org_id, user_id=user_id)
    assert page.total == 1
    assert page.items[0].body == "You were assigned a task."
    assert page.items[0].status == "delivered"
    assert page.items[0].delivered_at is not None
    assert await service.count_unread(org_id=org_id, user_id=user_id) == 1
    assert len(provider.messages) == 1

    async with session_factory() as session:
        attempt_count = (
            await session.execute(
                select(func.count()).select_from(
                    NotificationDeliveryAttemptOrmModel
                )
            )
        ).scalar_one()
    assert attempt_count == 1


async def test_sensitive_transactional_body_is_not_persisted_or_listed(
    notification_context,
) -> None:
    uow_factory, session_factory = notification_context
    recorder = SqlAlchemyNotificationDeliveryRecorder(uow_factory=uow_factory)
    dispatcher = NotificationDispatcher(
        email_provider=_EmailProvider(),
        delivery_recorder=recorder,
    )
    org_id = OrgId(new_uuid7())
    user_id = UserId(new_uuid7())
    one_time_token = "one-time-secret-token"

    await dispatcher.dispatch(
        NotificationRequest(
            org_id=org_id,
            channel=NotificationChannel.EMAIL,
            recipient="recipient@example.com",
            recipient_user_id=user_id,
            subject="Reset your password",
            body=f"https://app.example/reset?token={one_time_token}",
        )
    )

    page = await NotificationService(uow_factory=uow_factory).list_for_user(
        org_id=org_id, user_id=user_id
    )
    assert page.total == 0

    async with session_factory() as session:
        stored = (
            await session.execute(
                select(NotificationOrmModel).where(
                    NotificationOrmModel.recipient_user_id == user_id
                )
            )
        ).scalar_one()
    assert stored.body == ""
    assert stored.is_visible is False
    assert one_time_token not in stored.body
