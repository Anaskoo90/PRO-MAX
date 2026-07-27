"""
Base Specification pattern (Domain Modeling & DDD Blueprint) plus the
generic validation-framework entry point.

Concrete specifications (CanGrantPermissionSpecification,
SlaBreachRiskSpecification, RefundEligibilitySpecification, ...) live in
their owning bounded context and subclass Specification[T] from here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class Specification(ABC, Generic[T]):
    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool: ...

    def and_(self, other: "Specification[T]") -> "Specification[T]":
        return _AndSpecification(self, other)

    def or_(self, other: "Specification[T]") -> "Specification[T]":
        return _OrSpecification(self, other)

    def not_(self) -> "Specification[T]":
        return _NotSpecification(self)


class _AndSpecification(Specification[T]):
    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        self._left, self._right = left, right

    def is_satisfied_by(self, candidate: T) -> bool:
        return self._left.is_satisfied_by(candidate) and self._right.is_satisfied_by(candidate)


class _OrSpecification(Specification[T]):
    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        self._left, self._right = left, right

    def is_satisfied_by(self, candidate: T) -> bool:
        return self._left.is_satisfied_by(candidate) or self._right.is_satisfied_by(candidate)


class _NotSpecification(Specification[T]):
    def __init__(self, spec: Specification[T]) -> None:
        self._spec = spec

    def is_satisfied_by(self, candidate: T) -> bool:
        return not self._spec.is_satisfied_by(candidate)


class ValidationIssue:
    __slots__ = ("field", "message")

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message


class ValidationResult:
    __slots__ = ("issues",)

    def __init__(self, issues: list[ValidationIssue] | None = None) -> None:
        self.issues = issues or []

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def add(self, field: str, message: str) -> None:
        self.issues.append(ValidationIssue(field, message))
