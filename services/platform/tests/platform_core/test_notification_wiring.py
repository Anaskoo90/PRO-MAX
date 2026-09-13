"""Regression coverage for cross-context notification composition.

Transactional email is configured once by Identity. Downstream contexts
must reuse that dispatcher; constructing an empty dispatcher makes their
business flows fail (or silently skip delivery) despite valid SMTP settings.
"""

from app.main import identity_module, projects_module, tasks_module, workflow_engine_module


def test_email_capable_dispatcher_is_shared_by_every_notifying_context() -> None:
    dispatcher = identity_module.notification_dispatcher

    assert projects_module.notification_dispatcher is dispatcher
    assert tasks_module.notification_dispatcher is dispatcher
    assert workflow_engine_module.notification_dispatcher is dispatcher
