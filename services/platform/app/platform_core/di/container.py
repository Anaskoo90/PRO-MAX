"""
Service Registration + Lifecycle Management.

FastAPI's own Depends() handles request-scoped wiring at the route layer.
This container exists one layer down: it's how a bounded context's
composition root wires an interface (a Protocol/ABC from its domain layer)
to a concrete infrastructure implementation, with an explicit lifetime,
independent of any single HTTP framework — the application/domain layers
never import FastAPI.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from enum import StrEnum, auto
from typing import Any, Callable, TypeVar

T = TypeVar("T")

Factory = Callable[["ServiceContainer"], Any]


class Lifetime(StrEnum):
    SINGLETON = auto()
    SCOPED = auto()
    TRANSIENT = auto()


class ServiceNotRegisteredError(Exception):
    def __init__(self, service_type: type) -> None:
        super().__init__(f"No registration found for {service_type!r}")


class _Registration:
    __slots__ = ("factory", "lifetime")

    def __init__(self, factory: Factory, lifetime: Lifetime) -> None:
        self.factory = factory
        self.lifetime = lifetime


class ServiceContainer:
    def __init__(self, parent: "ServiceContainer | None" = None) -> None:
        self._registrations: dict[type, _Registration] = {}
        self._singletons: dict[type, Any] = {}
        self._scoped_instances: dict[type, Any] = {}
        self._parent = parent

    def register_singleton(self, service_type: type[T], factory: Factory) -> None:
        self._registrations[service_type] = _Registration(factory, Lifetime.SINGLETON)

    def register_scoped(self, service_type: type[T], factory: Factory) -> None:
        self._registrations[service_type] = _Registration(factory, Lifetime.SCOPED)

    def register_transient(self, service_type: type[T], factory: Factory) -> None:
        self._registrations[service_type] = _Registration(factory, Lifetime.TRANSIENT)

    def register_instance(self, service_type: type[T], instance: T) -> None:
        self._registrations[service_type] = _Registration(lambda c: instance, Lifetime.SINGLETON)
        self._singletons[service_type] = instance

    def _find_registration(self, service_type: type) -> _Registration:
        if service_type in self._registrations:
            return self._registrations[service_type]
        if self._parent is not None:
            return self._parent._find_registration(service_type)
        raise ServiceNotRegisteredError(service_type)

    def resolve(self, service_type: type[T]) -> T:
        registration = self._find_registration(service_type)

        if registration.lifetime == Lifetime.SINGLETON:
            owner = self._parent if self._parent is not None else self
            if service_type not in owner._singletons:
                owner._singletons[service_type] = registration.factory(self)
            return owner._singletons[service_type]

        if registration.lifetime == Lifetime.SCOPED:
            if service_type not in self._scoped_instances:
                self._scoped_instances[service_type] = registration.factory(self)
            return self._scoped_instances[service_type]

        return registration.factory(self)

    def create_scope(self) -> "ServiceContainer":
        """A child container: scoped registrations resolve once per scope
        (e.g. once per request), singletons still resolve to the root's
        single instance, transients still resolve fresh every call."""
        return ServiceContainer(parent=self)
