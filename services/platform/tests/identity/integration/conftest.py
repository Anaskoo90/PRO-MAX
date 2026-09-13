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
from app.identity.infrastructure.unit_of_work import IdentityUnitOfWork
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
        pytest.skip(
            f"No reachable test database at {TEST_DATABASE_URL} — "
            "run docker-compose + alembic upgrade head first"
        )
    finally:
        await engine.dispose()

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        session_factory = async_sessionmaker(
            connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with IdentityUnitOfWork(session_factory) as unit_of_work:
            yield unit_of_work
            await unit_of_work.rollback()
        # Application services exercise real commit paths, but the enclosing
        # transaction keeps every test isolated and makes repeated runs safe.
        await outer_transaction.rollback()
    await engine.dispose()
