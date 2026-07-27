"""
Result[T, E] pattern.

Application-layer command/query handlers return Result instead of raising
domain exceptions for *expected* failure cases (validation failures,
business rule violations) — exceptions remain reserved for genuinely
exceptional/infrastructure failures (see platform_core.errors). This keeps
expected failure paths visible in handler signatures instead of hidden in
try/except call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True


Result = Union[Ok[T], Err[E]]


def unwrap(result: Result[T, E]) -> T:
    """Raise ValueError if result is Err; use only where Err is unreachable."""
    if isinstance(result, Ok):
        return result.value
    raise ValueError(f"Called unwrap() on an Err: {result.error!r}")
