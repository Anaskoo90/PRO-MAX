import pytest

from app.platform_core.di.container import ServiceContainer, ServiceNotRegisteredError


class _Service:
    pass


def test_singleton_resolves_to_the_same_instance() -> None:
    container = ServiceContainer()
    container.register_singleton(_Service, lambda c: _Service())
    assert container.resolve(_Service) is container.resolve(_Service)


def test_transient_resolves_to_a_new_instance_each_time() -> None:
    container = ServiceContainer()
    container.register_transient(_Service, lambda c: _Service())
    assert container.resolve(_Service) is not container.resolve(_Service)


def test_scoped_resolves_once_per_scope_but_differs_across_scopes() -> None:
    root = ServiceContainer()
    root.register_scoped(_Service, lambda c: _Service())

    scope_a = root.create_scope()
    scope_b = root.create_scope()

    assert scope_a.resolve(_Service) is scope_a.resolve(_Service)
    assert scope_a.resolve(_Service) is not scope_b.resolve(_Service)


def test_unregistered_service_raises() -> None:
    container = ServiceContainer()
    with pytest.raises(ServiceNotRegisteredError):
        container.resolve(_Service)
