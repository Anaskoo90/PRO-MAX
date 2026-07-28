"""
Boards & Agile Management composition root.

Takes IdentityModule, ProjectsModule, and TasksModule as constructor
dependencies — the composition root is the one place cross-context wiring
is allowed. Reuses:
- Identity's real PermissionEvaluator instance (OrgPermissionCheckerPort,
  structural match, no adapter needed).
- Projects' own public ProjectService/ProjectMembershipService, wrapped by
  this context's own ProjectsProjectContextAdapter (an Anti-Corruption
  Layer, not a modification of Projects) — every context builds its own.
- Tasks' own public TaskService/TaskQueryService/TaskLifecycleService/
  TaskAssignmentService/LabelService, wrapped by this context's own
  TasksTaskContextAdapter.
- Platform Core's JobScheduler/JobExecutor (first exercised by Tasks) for
  a recurring daily burndown-snapshot job.
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
from app.projects.composition import ProjectsModule
from app.tasks.composition import TasksModule
from app.boards.application.backlog_management import BacklogService
from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.boards.application.column_management import ColumnService
from app.boards.application.estimate_management import EstimateService
from app.boards.application.sprint_management import SprintService
from app.boards.application.sprint_reporting import SprintReportingService
from app.boards.application.swimlane_management import SwimlaneService
from app.boards.infrastructure.projects_adapter import ProjectsProjectContextAdapter
from app.boards.infrastructure.seed_data import BOARDS_PERMISSION_CATALOG
from app.boards.infrastructure.tasks_adapter import TasksTaskContextAdapter
from app.boards.infrastructure.unit_of_work import BoardsUnitOfWork
from app.boards.presentation import (
    backlog_router,
    boards_router,
    cards_router,
    columns_router,
    deps,
    sprints_router,
    swimlanes_router,
)

_logger = get_logger("boards.composition")
_BURNDOWN_SNAPSHOT_INTERVAL_SECONDS = 86400.0


class BoardsModule:
    module_name = "boards"

    def __init__(
        self, settings: PlatformSettings, identity_module: IdentityModule, projects_module: ProjectsModule,
        tasks_module: TasksModule,
    ) -> None:
        self._settings = settings
        engine = create_async_engine(str(settings.database_url))
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

        self.dispatcher = EventDispatcher()

        def uow_factory() -> BoardsUnitOfWork:
            return BoardsUnitOfWork(self._session_factory)

        self._uow_factory = uow_factory

        # --- Cross-context wiring (composition root only) ---
        permission_checker = identity_module.permission_evaluator
        project_context = ProjectsProjectContextAdapter(
            project_service=projects_module.project_service,
            project_membership_service=projects_module.project_membership_service,
        )
        tasks_context = TasksTaskContextAdapter(
            task_service=tasks_module.task_service, task_query_service=tasks_module.task_query_service,
            task_lifecycle_service=tasks_module.task_lifecycle_service,
            task_assignment_service=tasks_module.task_assignment_service, label_service=tasks_module.label_service,
        )

        self.board_service = BoardService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.column_service = ColumnService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.swimlane_service = SwimlaneService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context, tasks_context=tasks_context,
        )
        self.card_movement_service = CardMovementService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context, tasks_context=tasks_context,
        )
        self.backlog_service = BacklogService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.sprint_service = SprintService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context, tasks_context=tasks_context,
        )
        self.sprint_reporting_service = SprintReportingService(uow_factory=uow_factory, tasks_context=tasks_context)
        self.estimate_service = EstimateService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )

        # --- Background Jobs (platform_core.jobs, reused from Tasks) ---
        self._job_executor = JobExecutor()
        self.job_scheduler = JobScheduler()
        self.job_scheduler.register(
            JobDefinition(
                name="boards_sprint_burndown_snapshot", func=self._record_daily_snapshots,
                interval_seconds=_BURNDOWN_SNAPSHOT_INTERVAL_SECONDS,
            )
        )

    async def _record_daily_snapshots(self) -> None:
        written = await self._job_executor.run(
            "boards_sprint_burndown_snapshot", self.sprint_reporting_service.record_daily_snapshots
        )
        await _logger.ainfo("boards_sprint_burndown_snapshot_complete", snapshots_written=written)

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(BoardService, self.board_service)
        container.register_instance(ColumnService, self.column_service)
        container.register_instance(SwimlaneService, self.swimlane_service)
        container.register_instance(CardMovementService, self.card_movement_service)
        container.register_instance(BacklogService, self.backlog_service)
        container.register_instance(SprintService, self.sprint_service)
        container.register_instance(SprintReportingService, self.sprint_reporting_service)
        container.register_instance(EstimateService, self.estimate_service)

    def mount(self, app: FastAPI) -> None:
        app.include_router(boards_router.router)
        app.include_router(columns_router.router)
        app.include_router(swimlanes_router.router)
        app.include_router(cards_router.router)
        app.include_router(backlog_router.router)
        app.include_router(sprints_router.router)

        app.dependency_overrides[deps.get_board_service] = lambda: self.board_service
        app.dependency_overrides[deps.get_column_service] = lambda: self.column_service
        app.dependency_overrides[deps.get_swimlane_service] = lambda: self.swimlane_service
        app.dependency_overrides[deps.get_card_movement_service] = lambda: self.card_movement_service
        app.dependency_overrides[deps.get_backlog_service] = lambda: self.backlog_service
        app.dependency_overrides[deps.get_sprint_service] = lambda: self.sprint_service
        app.dependency_overrides[deps.get_sprint_reporting_service] = lambda: self.sprint_reporting_service
        app.dependency_overrides[deps.get_estimate_service] = lambda: self.estimate_service


__all__ = ["BoardsModule", "BOARDS_PERMISSION_CATALOG"]
