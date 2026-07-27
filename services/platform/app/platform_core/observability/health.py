"""
Health / Readiness / Liveness Checks — semantics kept precisely distinct
(Architecture Review Extension §9):

- Liveness: is the process itself alive? No dependency checks — a failing
  liveness check means "restart this process."
- Readiness: can this process currently serve traffic? Checks dependencies
  (DB, Redis, RabbitMQ) — a failing readiness check means "stop routing
  traffic here, but don't restart."
- Health: a human/dashboard-facing superset of readiness with per-dependency
  detail, not used by the orchestrator for routing decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class DependencyCheckResult:
    name: str
    status: HealthStatus
    detail: str | None = None


DependencyCheck = Callable[[], Awaitable[DependencyCheckResult]]


class HealthCheckRegistry:
    def __init__(self) -> None:
        self._checks: list[DependencyCheck] = []

    def register(self, check: DependencyCheck) -> None:
        self._checks.append(check)

    async def liveness(self) -> HealthStatus:
        """No dependency checks by design — see module docstring."""
        return HealthStatus.HEALTHY

    async def readiness(self) -> HealthStatus:
        results = [await check() for check in self._checks]
        if any(r.status == HealthStatus.UNHEALTHY for r in results):
            return HealthStatus.UNHEALTHY
        if any(r.status == HealthStatus.DEGRADED for r in results):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    async def health_report(self) -> list[DependencyCheckResult]:
        return [await check() for check in self._checks]
