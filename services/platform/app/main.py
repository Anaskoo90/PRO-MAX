"""
Composition root: wires platform_core and every bounded context into a
single FastAPI application.

Each bounded context's composition module (e.g. app.identity.composition)
exposes `register(container)` + `mount(app)`, following the
ModuleRegistration protocol in platform_core.di.registration. Contexts
beyond Identity, Projects & Workspaces, and Tasks & Work Management (CRM,
Ticketing, ...) are not implemented yet.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from app.tasks.composition import TASKS_PERMISSION_CATALOG, TasksModule  # noqa: E402
from app.boards.composition import BOARDS_PERMISSION_CATALOG, BoardsModule  # noqa: E402
from app.workflow_engine.composition import WORKFLOW_PERMISSION_CATALOG, WorkflowEngineModule  # noqa: E402
from app.discord_integration.composition import DISCORD_PERMISSION_CATALOG, DiscordIntegrationModule  # noqa: E402
from app.discord_integration.settings import DiscordIntegrationSettings  # noqa: E402
from app.ticket_system.composition import TICKET_PERMISSION_CATALOG, TicketSystemModule  # noqa: E402

identity_module = IdentityModule(settings)
projects_module = ProjectsModule(settings, identity_module)
tasks_module = TasksModule(settings, identity_module, projects_module)
boards_module = BoardsModule(settings, identity_module, projects_module, tasks_module)
workflow_engine_module = WorkflowEngineModule(settings, identity_module, projects_module, tasks_module, boards_module)
discord_integration_module = DiscordIntegrationModule(DiscordIntegrationSettings(), identity_module)
ticket_system_module = TicketSystemModule(settings, identity_module, discord_integration_module)


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
    await identity_module.seed(
        extra_permissions=(
            *PROJECTS_PERMISSION_CATALOG, *TASKS_PERMISSION_CATALOG, *BOARDS_PERMISSION_CATALOG,
            *WORKFLOW_PERMISSION_CATALOG, *DISCORD_PERMISSION_CATALOG, *TICKET_PERMISSION_CATALOG,
        )
    )
    await tasks_module.job_scheduler.start()
    await boards_module.job_scheduler.start()
    await workflow_engine_module.job_scheduler.start()
    await logger.ainfo("platform_core_startup_complete", environment=settings.environment)
    try:
        yield
    finally:
        await workflow_engine_module.job_scheduler.stop()
        await boards_module.job_scheduler.stop()
        await tasks_module.job_scheduler.stop()
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
    if settings.cors_allowed_origins:
        # cors_allowed_origins was already declared on PlatformSettings (and
        # required in staging/production by its validator above) but never
        # actually wired to a middleware — the web dashboard is this
        # setting's first real consumer, since it's the first browser-based
        # client calling this API cross-origin.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    register_exception_handlers(app)

    identity_module.register(container)
    identity_module.mount(app)
    projects_module.register(container)
    projects_module.mount(app)
    tasks_module.register(container)
    tasks_module.mount(app)
    boards_module.register(container)
    boards_module.mount(app)
    workflow_engine_module.register(container)
    workflow_engine_module.mount(app)
    discord_integration_module.register(container)
    discord_integration_module.mount(app)
    ticket_system_module.register(container)
    ticket_system_module.mount(app)

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
        # DependencyCheckResult is a frozen, slotted dataclass (no __dict__);
        # asdict() is the slots-safe way to serialize it.
        return {"checks": [asdict(r) for r in report]}

    return app


app = create_app()
