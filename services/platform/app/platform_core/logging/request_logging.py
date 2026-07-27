"""Request Logging middleware: one structured log line per HTTP request."""

from __future__ import annotations

import time

from app.platform_core.logging.logger import get_logger

_logger = get_logger("http.request")


class RequestLoggingMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        await _logger.ainfo(
            "http_request_completed",
            method=scope.get("method"),
            path=scope.get("path"),
            status_code=status_holder.get("status"),
            duration_ms=duration_ms,
        )
