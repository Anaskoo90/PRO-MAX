"""
Dependency Validation: walk every registered factory's declared
dependencies (via typed constructor inspection) and fail startup if
something is unresolvable — catching a missing registration at boot,
not on the first request that happens to exercise that code path.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

from app.platform_core.di.container import ServiceContainer


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    service_type: type
    missing_dependency: type


def validate_container(container: ServiceContainer) -> list[ValidationIssue]:
    """Best-effort static check: for every registered factory, inspect its
    signature and confirm each annotated parameter type is itself
    resolvable. Factories that take the container directly (the common
    `lambda c: Impl(c.resolve(Interface))` shape) are opaque to this
    inspection and are skipped — this validates constructor-injected
    concrete classes registered via register_singleton/scoped/transient
    with a class reference as the factory.
    """
    issues: list[ValidationIssue] = []
    for service_type, registration in container._registrations.items():  # noqa: SLF001
        factory = registration.factory
        target = factory
        if not inspect.isclass(target):
            continue
        try:
            signature = inspect.signature(target.__init__)
        except (TypeError, ValueError):
            continue
        for name, param in signature.parameters.items():
            if name == "self" or param.annotation is inspect.Parameter.empty:
                continue
            try:
                container._find_registration(param.annotation)  # noqa: SLF001
            except Exception:
                issues.append(ValidationIssue(service_type, param.annotation))
    return issues


def assert_container_valid(container: ServiceContainer) -> None:
    issues = validate_container(container)
    if issues:
        details = "\n".join(
            f"  - {i.service_type} depends on unregistered {i.missing_dependency}"
            for i in issues
        )
        raise RuntimeError(f"Dependency Injection validation failed:\n{details}")
