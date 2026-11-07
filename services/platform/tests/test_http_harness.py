"""The HTTP harness must not depend on test order: older tests that pop their own stub from
`app.dependency_overrides` also remove the app's real override, and the harness has to put it back."""

from __future__ import annotations

from app.identity.presentation import deps
from app.main import app

from tests.http_harness import _PRISTINE_WIRING, restore_app_wiring


def test_the_apps_real_wiring_was_captured_at_import() -> None:
    assert deps.get_organization_invitation_service in _PRISTINE_WIRING
    assert deps.get_authentication_service in _PRISTINE_WIRING


def test_restore_app_wiring_repairs_a_popped_override() -> None:
    original = app.dependency_overrides.get(deps.get_organization_invitation_service)
    try:
        app.dependency_overrides.pop(deps.get_organization_invitation_service, None)  # what the older tests do

        restore_app_wiring()

        assert app.dependency_overrides[deps.get_organization_invitation_service] is _PRISTINE_WIRING[
            deps.get_organization_invitation_service
        ]
    finally:
        restore_app_wiring()
        assert original is None or app.dependency_overrides.get(deps.get_organization_invitation_service) is not None


def test_restore_app_wiring_removes_a_leftover_stub() -> None:
    try:
        app.dependency_overrides[deps.get_security_service] = lambda: "a stub left behind"

        restore_app_wiring()

        assert app.dependency_overrides.get(deps.get_security_service) is _PRISTINE_WIRING.get(deps.get_security_service)
    finally:
        restore_app_wiring()
