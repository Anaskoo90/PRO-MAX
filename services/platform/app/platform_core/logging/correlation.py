"""
Correlation ID propagation via contextvars, so it's available to structured
log calls anywhere in the async call stack without threading it through
every function signature.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from app.platform_core.shared_kernel.constants import HEADER_CORRELATION_ID

_correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    _correlation_id_var.set(correlation_id)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


class CorrelationIdMiddleware:
    """ASGI middleware: reads X-Correlation-Id if present, else mints one,
    binds it to the contextvar for the duration of the request, and echoes
    it back on the response."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw = headers.get(HEADER_CORRELATION_ID.lower().encode())
        correlation_id = raw.decode() if raw else new_correlation_id()
        token = _correlation_id_var.set(correlation_id)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append(
                    (HEADER_CORRELATION_ID.encode(), correlation_id.encode())
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            _correlation_id_var.reset(token)
