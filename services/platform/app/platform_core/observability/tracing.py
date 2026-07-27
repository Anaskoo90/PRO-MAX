"""Tracing: OpenTelemetry tracer + a decorator for wrapping application-layer
command/query handlers in a span, so every handler shows up in a trace
without manual instrumentation at every call site."""

from __future__ import annotations

import functools
from typing import Awaitable, Callable, TypeVar

from opentelemetry import trace

_tracer = trace.get_tracer("guilddesk.platform")

T = TypeVar("T")


def traced(span_name: str | None = None) -> Callable[
    [Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]
]:
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        name = span_name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            with _tracer.start_as_current_span(name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def get_tracer() -> trace.Tracer:
    return _tracer
