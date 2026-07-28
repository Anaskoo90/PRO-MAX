"""
Thin async HTTP client for the GuildDesk platform API.

This is the *only* file allowed to know the shape of the backend's HTTP
responses — cogs never call httpx directly, they call methods on
ApiClient, exactly the same boundary discipline the backend itself uses
for its own Anti-Corruption Layers between bounded contexts.

One instance is constructed for the lifetime of the bot process (see
client.py) and reused across every command invocation, rather than opening
a new connection per interaction.
"""

from __future__ import annotations

import httpx


class ApiClient:
    def __init__(self, *, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def check_health(self) -> bool:
        """GET /health — the platform's dependency-level health report
        (see app/main.py). That endpoint always answers 200 even when a
        dependency is down; it reports per-check status inside the body
        (`{"checks": [{"status": "healthy" | "degraded" | "unhealthy", ...}]}`),
        never via the HTTP status code — so a real health determination
        has to look at the body, not just "did we get a response".
        Any transport failure, non-2xx response, or unparseable body is
        treated as "unhealthy" rather than raised: a Discord command
        handler needs a clean boolean to render a status message, not an
        exception to catch at every call site."""
        try:
            response = await self._http.get("/health")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return False
        checks = payload.get("checks", [])
        return len(checks) > 0 and all(check.get("status") == "healthy" for check in checks)

    async def aclose(self) -> None:
        await self._http.aclose()
