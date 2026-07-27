"""
Composition root: wires platform_core and every bounded context into a
single FastAPI application.

Each bounded context's composition module (e.g. app.identity.composition)
exposes `register(container)` + `mount(app)`, following the
ModuleRegistration protocol in platform_core.di.registration. Contexts
beyond Identity and Projects & Workspaces (CRM, Ticketing, Engineering
Workspace, ...) are not implemented yet.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.platform_core.configuration.settings import get_settings
from app.platform_core.di.container import ServiceContainer
from app.platform_core.di.lifecycle import LifecycleManager
from app.platform_core.errors.handlers import register_exception_handlers
from app.platform_core.logging.correlation import CorrelationIdMiddleware
from app.platform_core.logging.logger import configure_logging, get_logger
from app.platform_core.logging.request_logging import RequestLoggingMiddleware
from app.platform_core.observability.health import (
    DependencyCheckResult,
    HealthCheckRegistry,
    HealthStatus,
)

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger("app.main")

container = ServiceContainer()
lifecycle = LifecycleManager()
health_registry = HealthCheckRegistry()

from app.identity.composition import IdentityModule  # noqa: E402  (after settings/logging setup)
from app.projects.composition import PROJECTS_PERMISSION_CATALOG, ProjectsModule  # noqa: E402

identity_module = IdentityModule(settings)
projects_module = ProjectsModule(settings, identity_module)


@asynccontextmanager
async def _db_engine():
    engine = create_async_engine(str(settings.database_url))
    container.register_instance(AsyncEngine, engine)

    async def _check() -> DependencyCheckResult:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return DependencyCheckResult(name="database", status=HealthStatus.HEALTHY)
        except Exception as exc:
            return DependencyCheckResult(
                name="database", status=HealthStatus.UNHEALTHY, detail=str(exc)
            )

    health_registry.register(_check)
    try:
        yield engine
    finally:
        await engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    lifecycle.register(_db_engine)
    await lifecycle.startup()
    await identity_module.seed(extra_permissions=PROJECTS_PERMISSION_CATALOG)
    await logger.ainfo("platform_core_startup_complete", environment=settings.environment)
    try:
        yield
    finally:
        await lifecycle.shutdown()
        await logger.ainfo("platform_core_shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="GuildDesk Platform",
        version=settings.api_version,
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    identity_module.register(container)
    identity_module.mount(app)
    projects_module.register(container)
    projects_module.mount(app)

    @app.get("/health/live", tags=["observability"])
    async def liveness() -> dict[str, str]:
        status = await health_registry.liveness()
        return {"status": status.value}

    @app.get("/health/ready", tags=["observability"])
    async def readiness() -> dict[str, str]:
        status = await health_registry.readiness()
        return {"status": status.value}

    @app.get("/health", tags=["observability"])
    async def health() -> dict[str, object]:
        report = await health_registry.health_report()
        return {"checks": [r.__dict__ for r in report]}

    return app


app = create_app()
