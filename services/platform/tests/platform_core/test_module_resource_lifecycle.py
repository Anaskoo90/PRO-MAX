from __future__ import annotations

import pytest
from app.boards.composition import BoardsModule
from app.discord_integration.composition import DiscordIntegrationModule
from app.identity.composition import IdentityModule
from app.main import app, health_registry
from app.notifications.composition import NotificationsModule
from app.platform_core.observability.health import DependencyCheckResult, HealthStatus
from app.projects.composition import ProjectsModule
from app.tasks.composition import TasksModule
from app.ticket_system.composition import TicketSystemModule
from app.workflow_engine.composition import WorkflowEngineModule
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio
client = TestClient(app)


class _Engine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class _Redis:
    def __init__(self, *, ping_result: bool = True, error: Exception | None = None) -> None:
        self.ping_result = ping_result
        self.error = error
        self.closed = False

    async def ping(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.ping_result

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "module_type",
    [
        NotificationsModule,
        ProjectsModule,
        TasksModule,
        BoardsModule,
        WorkflowEngineModule,
        DiscordIntegrationModule,
        TicketSystemModule,
    ],
)
async def test_context_shutdown_disposes_its_database_engine(module_type) -> None:
    module = module_type.__new__(module_type)
    module._engine = _Engine()

    await module.shutdown()

    assert module._engine.disposed is True


async def test_identity_shutdown_closes_redis_and_database_engine() -> None:
    module = IdentityModule.__new__(IdentityModule)
    module.redis_client = _Redis()
    module._engine = _Engine()

    await module.shutdown()

    assert module.redis_client.closed is True
    assert module._engine.disposed is True


async def test_redis_health_check_reports_healthy_dependency() -> None:
    module = IdentityModule.__new__(IdentityModule)
    module.redis_client = _Redis()

    result = await module.redis_health_check()

    assert result.name == "redis"
    assert result.status == HealthStatus.HEALTHY
    assert result.detail is None


@pytest.mark.parametrize(
    ("redis", "expected_detail"),
    [
        (_Redis(ping_result=False), "did not return"),
        (_Redis(error=ConnectionError("redis unavailable")), "redis unavailable"),
    ],
)
async def test_redis_health_check_reports_unhealthy_dependency(
    redis: _Redis, expected_detail: str
) -> None:
    module = IdentityModule.__new__(IdentityModule)
    module.redis_client = redis

    result = await module.redis_health_check()

    assert result.name == "redis"
    assert result.status == HealthStatus.UNHEALTHY
    assert expected_detail in (result.detail or "")


async def _unhealthy_dependency() -> DependencyCheckResult:
    return DependencyCheckResult(name="test", status=HealthStatus.UNHEALTHY)


async def test_readiness_returns_service_unavailable_for_an_unhealthy_dependency() -> None:
    original_checks = health_registry._checks
    health_registry._checks = [_unhealthy_dependency]
    try:
        response = client.get("/health/ready")
    finally:
        health_registry._checks = original_checks

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}
