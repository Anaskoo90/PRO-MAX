"""
HTTP-based implementation of WebhookExecutorPort — the EXECUTE_WEBHOOK
workflow action. No other bounded context has needed outbound HTTP before,
so this is a new, self-contained capability introduced within Workflow
Engine's own infrastructure (not a Platform Core change) — the same kind
of first-use-introduces-the-infra precedent Tasks set for JobScheduler and
Boards set for the daily burndown job.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.platform_core.shared_kernel.constants import TIMEOUT_EXTERNAL_SECONDS
from app.workflow_engine.domain.exceptions import WebhookExecutionFailedError


class HttpxWebhookExecutor:
    def __init__(self, *, timeout_seconds: float = TIMEOUT_EXTERNAL_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    async def execute(self, *, url: str, payload: dict[str, Any]) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WebhookExecutionFailedError(f"Webhook POST to '{url}' failed: {exc}") from exc
