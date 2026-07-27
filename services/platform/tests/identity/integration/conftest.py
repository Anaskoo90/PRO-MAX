"""
Integration test fixtures — these hit a real PostgreSQL instance (the
`docker-compose.yml` at infrastructure/docker/, migrated via
`alembic upgrade head`) rather than fakes, exercising the actual
SQLAlchemy repository implementations and the Alembic migration together.

Skipped automatically if GUILDDESK_TEST_DATABASE_URL isn't set/reachable —
these are not run as part of the default `pytest` invocation used for the
fast unit suite, only under `task test:integration` (docker-compose up
first).
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.infrastructure.unit_of_work import IdentityUnitOfWork

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
    async with IdentityUnitOfWork(session_factory) as unit_of_work:
        yield unit_of_work
        await unit_of_work.rollback()  # never persist test data past the test
    await engine.dispose()
