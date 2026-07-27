"""
Base structural interfaces for the DDD tactical patterns (ADR-005..009).

These are Protocols, not ABCs: bounded-context domain models satisfy them
structurally, without importing platform_core as a runtime base class. That
keeps the domain layer's only real dependency on platform_core to this one
module, which is the intended narrow waist of the Clean Architecture
dependency rule.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Generic, Protocol, TypeVar, runtime_checkable

from app.platform_core.shared_kernel.types import EntityId

T = TypeVar("T")
TEntity = TypeVar("TEntity", bound="Entity")


@runtime_checkable
class Entity(Protocol):
    id: EntityId


@runtime_checkable
class AggregateRoot(Entity, Protocol):
    version: int

    def pull_domain_events(self) -> list[object]:
        """Drain and return events recorded since the last pull."""
        ...


class ValueObject(Protocol):
    """Marker protocol: equality is by value, instances are immutable."""


class Repository(Protocol[TEntity]):
    @abstractmethod
    async def get_by_id(self, entity_id: EntityId) -> TEntity | None: ...

    @abstractmethod
    async def add(self, entity: TEntity) -> None: ...

    @abstractmethod
    async def remove(self, entity: TEntity) -> None: ...


class UnitOfWork(Protocol):
    """Transaction boundary spanning one or more repositories."""

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
