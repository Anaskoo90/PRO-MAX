"""
Shared FastAPI dependencies for the Tasks & Work Management presentation
layer.

Authentication is *not* reimplemented here — `get_current_user_claims` is
imported directly from app.identity.presentation.deps, same reuse pattern
Projects & Workspaces already established (both contexts sit behind the
same FastAPI app and the same JwtTokenService instance).
"""

from __future__ import annotations

from app.identity.presentation.deps import get_current_user_claims  # noqa: F401  (re-exported for routers)
from app.tasks.application.label_management import LabelService
from app.tasks.application.task_assignment import TaskAssignmentService
from app.tasks.application.task_lifecycle import TaskLifecycleService
from app.tasks.application.task_management import TaskService
from app.tasks.application.task_ordering import TaskOrderingService
from app.tasks.application.task_query_service import TaskQueryService
from app.tasks.application.task_relationships import TaskRelationshipService
from app.tasks.application.task_scheduling import TaskSchedulingService
from app.tasks.application.workflow_management import WorkflowService


def get_task_service() -> TaskService:
    raise NotImplementedError("TaskService dependency not wired")


def get_task_query_service() -> TaskQueryService:
    raise NotImplementedError("TaskQueryService dependency not wired")


def get_task_lifecycle_service() -> TaskLifecycleService:
    raise NotImplementedError("TaskLifecycleService dependency not wired")


def get_task_scheduling_service() -> TaskSchedulingService:
    raise NotImplementedError("TaskSchedulingService dependency not wired")


def get_task_assignment_service() -> TaskAssignmentService:
    raise NotImplementedError("TaskAssignmentService dependency not wired")


def get_label_service() -> LabelService:
    raise NotImplementedError("LabelService dependency not wired")


def get_task_relationship_service() -> TaskRelationshipService:
    raise NotImplementedError("TaskRelationshipService dependency not wired")


def get_task_ordering_service() -> TaskOrderingService:
    raise NotImplementedError("TaskOrderingService dependency not wired")


def get_workflow_service() -> WorkflowService:
    raise NotImplementedError("WorkflowService dependency not wired")
