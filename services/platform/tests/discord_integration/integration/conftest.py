"""Integration test fixtures for Discord Integration — same pattern as
tests/boards/integration/conftest.py: hits a real PostgreSQL instance
(migrated via `alembic upgrade head`, which now includes 0007's
`discord_integration` schema), skipped automatically if unreachable."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.discord_integration.infrastructure.unit_of_work import DiscordIntegrationUnitOfWork

TEST_DATABASE_URL = os.environ.get(
    "GUILDDESK_TEST_DATABASE_URL", "postgresql+asyncpg://guilddesk:guilddesk@localhost:5432/guilddesk_test"
)


@pytest_asyncio.fixture
async def uow():
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect():
            pass
    except Exception:
        pytest.skip(f"No reachable test database at {TEST_DATABASE_URL} — run docker-compose + alembic upgrade head first")
    finally:
        await engine.dispose()

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with DiscordIntegrationUnitOfWork(session_factory) as unit_of_work:
        yield unit_of_work
        await unit_of_work.rollback()
    await engine.dispose()
