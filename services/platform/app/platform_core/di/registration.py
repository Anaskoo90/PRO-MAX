"""
Module Registration: the contract every bounded context implements so the
composition root (app/main.py) can wire all contexts uniformly, e.g.:

    from app.identity.composition import IdentityModule
    from app.crm.composition import CrmModule

    for module in (IdentityModule(), CrmModule(), ...):
        module.register(container)
"""

from __future__ import annotations

from typing import Protocol

from app.platform_core.di.container import ServiceContainer


class ModuleRegistration(Protocol):
    module_name: str

    def register(self, container: ServiceContainer) -> None: ...


def register_all(container: ServiceContainer, modules: list[ModuleRegistration]) -> None:
    for module in modules:
        module.register(container)
