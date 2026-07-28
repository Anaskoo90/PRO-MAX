"""
Shared FastAPI dependencies for the Workflow Engine presentation layer.

Authentication is *not* reimplemented here — `get_current_user_claims` is
imported directly from app.identity.presentation.deps, same reuse pattern
every prior context has established.
"""

from __future__ import annotations

from app.identity.presentation.deps import get_current_user_claims  # noqa: F401  (re-exported for routers)
from app.workflow_engine.application.execution_service import WorkflowExecutionService
from app.workflow_engine.application.state_management import WorkflowStateService
from app.workflow_engine.application.transition_management import WorkflowTransitionService
from app.workflow_engine.application.workflow_management import WorkflowService


def get_workflow_service() -> WorkflowService:
    raise NotImplementedError("WorkflowService dependency not wired")


def get_workflow_state_service() -> WorkflowStateService:
    raise NotImplementedError("WorkflowStateService dependency not wired")


def get_workflow_transition_service() -> WorkflowTransitionService:
    raise NotImplementedError("WorkflowTransitionService dependency not wired")


def get_workflow_execution_service() -> WorkflowExecutionService:
    raise NotImplementedError("WorkflowExecutionService dependency not wired")
