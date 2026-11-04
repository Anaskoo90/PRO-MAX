"""Real-application HTTP test harness.

Drives the actual FastAPI app (all routers, middleware, error handlers and
the modules' own database engines) over HTTP, in-process, against the test
PostgreSQL database. Unlike the rolled-back-transaction fixtures used
elsewhere in the suite, the app opens its own connections, so the data these
tests need has to be *committed*; everything created is deleted again at
teardown.

Notes for writing tests with it
- Use `pytest.mark.asyncio(loop_scope="session")` on the tests (and this
  fixture is session-loop scoped): the app's module-level engines pool
  connections bound to the event loop that first used them, so every test
  that goes through them must share one loop.
- Each test gets its own client IP, so the per-IP login rate limiter (Redis)
  never leaks between tests or runs.
- The lifespan is not run (it needs RabbitMQ); no test here depends on it.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio
from app.identity.domain.entities import User
from app.identity.domain.organization import Organization
from app.identity.domain.value_objects import Email
from app.identity.infrastructure.unit_of_work import IdentityUnitOfWork
from app.main import app, identity_module, settings
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

API = "/api/v1"
PASSWORD = "Correct-Horse-Battery-9"
_SCHEMAS_EXCLUDED = ("pg_catalog", "information_schema")


@dataclass
class Tenant:
    org_id: OrgId
    slug: str
    user: User
    email: str


@dataclass
class HttpHarness:
    client: httpx.AsyncClient
    make_uow: object
    org_ids: list = field(default_factory=list)

    # ---- data -----------------------------------------------------------------
    async def create_tenant(self, tag: str = "t") -> Tenant:
        """An ACTIVE organization with one verified, ACTIVE member."""
        token = uuid.uuid4().hex[:10]
        slug, email = f"{tag}-{token}", f"{tag}-{token}@example.com"
        org = Organization.create(name=f"{tag} org", slug=slug, owner_user_id=UserId(new_uuid7()))
        org_id = OrgId(org.id)
        user = User.register(
            org_id=org_id, email=Email(email), password_hash=PasswordHashingService().hash(PASSWORD),
            display_name=tag,
        )
        user.verify_email()
        org.owner_user_id = UserId(user.id)
        async with self.make_uow() as uow:
            await uow.organizations.add(org)
            await uow.flush()
            await uow.users.add(user)
            await uow.commit()
        self.org_ids.append(org.id)
        return Tenant(org_id=org_id, slug=slug, user=user, email=email)

    # ---- organization status (through the application's own service) ---------
    @property
    def _orgs(self):
        return identity_module.organization_management_service

    async def suspend(self, tenant: Tenant) -> None:
        await self._orgs.suspend(org_id=tenant.org_id, actor_user_id=tenant.user.id)

    async def deactivate(self, tenant: Tenant) -> None:
        await self._orgs.deactivate(org_id=tenant.org_id, actor_user_id=tenant.user.id)

    async def reactivate(self, tenant: Tenant) -> None:
        await self._orgs.reactivate(org_id=tenant.org_id, actor_user_id=tenant.user.id)

    # ---- HTTP -----------------------------------------------------------------
    async def login(self, tenant: Tenant, *, password: str = PASSWORD) -> httpx.Response:
        return await self.client.post(
            f"{API}/auth/login", json={"org_slug": tenant.slug, "email": tenant.email, "password": password}
        )

    async def login_ok(self, tenant: Tenant) -> dict:
        response = await self.login(tenant)
        assert response.status_code == 200, response.text
        return response.json()

    @staticmethod
    def bearer(tokens: dict) -> dict:
        return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _cleanup(engine, org_ids: list) -> None:
    """Best-effort removal of everything created for `org_ids`, across every
    schema: rows keyed by org_id, rows keyed only by user_id, then users and
    organizations. Repeats until a pass has no FK failures (tables are
    discovered from information_schema, so new contexts are covered)."""
    if not org_ids:
        return
    async with engine.connect() as connection:
        columns = (
            await connection.execute(
                text(
                    "SELECT table_schema, table_name, column_name FROM information_schema.columns "
                    "WHERE column_name IN ('org_id', 'user_id') AND table_schema NOT IN :excluded "
                    "AND table_name IN (SELECT table_name FROM information_schema.tables "
                    "WHERE table_type = 'BASE TABLE' AND table_schema = information_schema.columns.table_schema)"
                ).bindparams(bindparam("excluded", value=_SCHEMAS_EXCLUDED, expanding=True))
            )
        ).all()
    by_table: dict[tuple[str, str], set[str]] = {}
    for schema, table, column in columns:
        by_table.setdefault((schema, table), set()).add(column)
    users_in_orgs = "(SELECT id FROM identity.users WHERE org_id IN :ids)"
    statements: list[str] = []
    for (schema, table), cols in sorted(by_table.items()):
        if (schema, table) in (("identity", "users"), ("identity", "organizations")):
            continue
        if "org_id" in cols:
            statements.append(f'DELETE FROM "{schema}"."{table}" WHERE org_id IN :ids')
        elif "user_id" in cols:
            statements.append(f'DELETE FROM "{schema}"."{table}" WHERE user_id IN {users_in_orgs}')
    statements += [
        "DELETE FROM identity.users WHERE org_id IN :ids",
        "DELETE FROM identity.organizations WHERE id IN :ids",
    ]
    pending = statements
    for _ in range(8):
        failed: list[str] = []
        for statement in pending:
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(statement).bindparams(bindparam("ids", value=org_ids, expanding=True))
                    )
            except Exception:  # an FK still blocks this one; retry after its dependants are gone
                failed.append(statement)
        if not failed:
            return
        pending = failed


@pytest_asyncio.fixture(loop_scope="session")
async def http_env():
    engine = create_async_engine(str(settings.database_url))
    try:
        async with engine.connect():
            pass
    except Exception:
        await engine.dispose()
        pytest.skip("No reachable test database for the HTTP harness")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    client_ip = f"10.{random.randint(1, 250)}.{random.randint(1, 250)}.{random.randint(1, 250)}"
    transport = httpx.ASGITransport(app=app, client=(client_ip, 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        harness = HttpHarness(client=client, make_uow=lambda: IdentityUnitOfWork(session_factory))
        yield harness
    await _cleanup(engine, harness.org_ids)
    await engine.dispose()
