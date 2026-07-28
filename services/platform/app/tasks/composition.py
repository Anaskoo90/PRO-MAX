"""
Tasks & Work Management composition root.

Takes both the already-constructed IdentityModule and ProjectsModule as
constructor dependencies — the composition root is the one place cross-
context wiring is allowed. Reuses:
- Identity's real PermissionEvaluator instance (OrgPermissionCheckerPort,
  structural match, no adapter needed).
- Projects' own public ProjectService/ProjectMembershipService, wrapped by
  this context's own ProjectsProjectContextAdapter (an Anti-Corruption
  Layer, not a modification of Projects).
- Projects' own IdentityUserDirectoryAdapter class, reused as-is (not
  copied) for the assignment-notification email lookup — one ACL class
  serving two downstream contexts.
- Platform Core's JobScheduler/JobExecutor (never used by Identity or
  Projects) for a recurring, read-only overdue-task observability job —
  the first bounded context to actually exercise that platform_core module.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.composition import IdentityModule
from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.di.container import ServiceContainer
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.jobs.executor import JobExecutor
from app.platform_core.jobs.scheduler import JobDefinition, JobScheduler
from app.platform_core.logging.logger import get_logger
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.projects.composition import ProjectsModule
from app.projects.infrastructure.identity_adapter import IdentityUserDirectoryAdapter
from app.tasks.application.label_management import LabelService
from app.tasks.application.task_assignment import TaskAssignmentService
from app.tasks.application.task_lifecycle import TaskLifecycleService
from app.tasks.application.task_management import TaskService
from app.tasks.application.task_ordering import TaskOrderingService
from app.tasks.application.task_query_service import TaskQueryService
from app.tasks.application.task_relationships import TaskRelationshipService
from app.tasks.application.task_scheduling import TaskSchedulingService
from app.tasks.application.workflow_management import WorkflowService
from app.tasks.infrastructure.projects_adapter import ProjectsProjectContextAdapter
from app.tasks.infrastructure.seed_data import TASKS_PERMISSION_CATALOG
from app.tasks.infrastructure.unit_of_work import TasksUnitOfWork
from app.tasks.presentation import (
    assignment_router,
    deps,
    labels_router,
    ordering_router,
    relationships_router,
    tasks_router,
    workflow_router,
)

_logger = get_logger("tasks.composition")
_OVERDUE_SCAN_INTERVAL_SECONDS = 3600.0


class TasksModule:
    module_name = "tasks"

    def __init__(self, settings: PlatformSettings, identity_module: IdentityModule, projects_module: ProjectsModule) -> None:
        self._settings = settings
        engine = create_async_engine(str(settings.database_url))
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

        self.dispatcher = EventDispatcher()
        self.notification_dispatcher = NotificationDispatcher()

        def uow_factory() -> TasksUnitOfWork:
            return TasksUnitOfWork(self._session_factory)

        self._uow_factory = uow_factory

        # --- Cross-context wiring (composition root only) ---
        permission_checker = identity_module.permission_evaluator
        project_context = ProjectsProjectContextAdapter(
            project_service=projects_module.project_service,
            project_membership_service=projects_module.project_membership_service,
        )
        user_directory = IdentityUserDirectoryAdapter(identity_module.create_unit_of_work)

        self.task_service = TaskService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.task_query_service = TaskQueryService(uow_factory=uow_factory)
        self.task_lifecycle_service = TaskLifecycleService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.task_scheduling_service = TaskSchedulingService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.task_assignment_service = TaskAssignmentService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context, notification_dispatcher=self.notification_dispatcher,
            user_directory=user_directory,
        )
        self.label_service = LabelService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.task_relationship_service = TaskRelationshipService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.task_ordering_service = TaskOrderingService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.workflow_service = WorkflowService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
        )

        # --- Background Jobs (platform_core.jobs — first bounded context to use it) ---
        self._job_executor = JobExecutor()
        self.job_scheduler = JobScheduler()
        self.job_scheduler.register(
            JobDefinition(
                name="tasks_overdue_scan", func=self._scan_overdue_tasks, interval_seconds=_OVERDUE_SCAN_INTERVAL_SECONDS
            )
        )

    async def _scan_overdue_tasks(self) -> None:
        """Read-only observability job — counts overdue tasks platform-wide
        and logs the result. Idempotent and side-effect-free, safe to run
        on any schedule without state-tracking concerns."""
        count = await self._job_executor.run(
            "tasks_overdue_scan", self.task_scheduling_service.count_overdue_all
        )
        await _logger.ainfo("tasks_overdue_scan_complete", overdue_count=count)

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(TaskService, self.task_service)
        container.register_instance(TaskQueryService, self.task_query_service)
        container.register_instance(TaskLifecycleService, self.task_lifecycle_service)
        container.register_instance(TaskSchedulingService, self.task_scheduling_service)
        container.register_instance(TaskAssignmentService, self.task_assignment_service)
        container.register_instance(LabelService, self.label_service)
        container.register_instance(TaskRelationshipService, self.task_relationship_service)
        container.register_instance(TaskOrderingService, self.task_ordering_service)
        container.register_instance(WorkflowService, self.workflow_service)

    def mount(self, app: FastAPI) -> None:
        app.include_router(tasks_router.router)
        app.include_router(assignment_router.router)
        app.include_router(labels_router.router)
        app.include_router(relationships_router.router)
        app.include_router(ordering_router.router)
        app.include_router(workflow_router.router)

        app.dependency_overrides[deps.get_task_service] = lambda: self.task_service
        app.dependency_overrides[deps.get_task_query_service] = lambda: self.task_query_service
        app.dependency_overrides[deps.get_task_lifecycle_service] = lambda: self.task_lifecycle_service
        app.dependency_overrides[deps.get_task_scheduling_service] = lambda: self.task_scheduling_service
        app.dependency_overrides[deps.get_task_assignment_service] = lambda: self.task_assignment_service
        app.dependency_overrides[deps.get_label_service] = lambda: self.label_service
        app.dependency_overrides[deps.get_task_relationship_service] = lambda: self.task_relationship_service
        app.dependency_overrides[deps.get_task_ordering_service] = lambda: self.task_ordering_service
        app.dependency_overrides[deps.get_workflow_service] = lambda: self.workflow_service


__all__ = ["TasksModule", "TASKS_PERMISSION_CATALOG"]
