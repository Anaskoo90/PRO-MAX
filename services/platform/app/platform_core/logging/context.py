"""Log Context: additional structured fields bound for the current task/request."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_log_context_var: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


def get_log_context() -> dict[str, Any]:
    return dict(_log_context_var.get())


@contextmanager
def bind_log_context(**fields: Any) -> Iterator[None]:
    """Merge fields into the current log context for the duration of the block,
    restoring the previous context on exit."""
    current = _log_context_var.get()
    token = _log_context_var.set({**current, **fields})
    try:
        yield
    finally:
        _log_context_var.reset(token)
