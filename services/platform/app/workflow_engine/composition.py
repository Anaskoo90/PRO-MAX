"""
Workflow Engine composition root.

Takes IdentityModule, ProjectsModule, TasksModule, and BoardsModule as
constructor dependencies — the composition root is the one place cross-
context wiring is allowed. Reuses:
- Identity's real PermissionEvaluator instance (OrgPermissionCheckerPort,
  structural match, no adapter needed).
- Projects' own public ProjectService/ProjectMembershipService, wrapped by
  this context's own ProjectsWorkflowContextAdapter.
- Tasks' own public TaskService/TaskLifecycleService/TaskSchedulingService/
  TaskAssignmentService/LabelService, wrapped by this context's own
  TasksWorkflowContextAdapter.
- Boards' own public BoardService/CardMovementService, wrapped by this
  context's own BoardsWorkflowContextAdapter — used only to evaluate the
  BOARD/SPRINT workflow conditions.
- Projects' own IdentityUserDirectoryAdapter class, reused as-is (not
  copied) for the SEND_NOTIFICATION action's recipient email lookup — the
  same one ACL class already serving Projects and Tasks.
- Platform Core's JobScheduler/JobExecutor (first exercised by Tasks, then
  Boards) for the recurring scheduled/delayed-action automation job.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.boards.composition import BoardsModule
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
from app.tasks.composition import TasksModule
from app.workflow_engine.application.action_execution import ActionExecutor
from app.workflow_engine.application.automation_service import WorkflowAutomationService
from app.workflow_engine.application.execution_service import WorkflowExecutionService
from app.workflow_engine.application.rule_evaluation import RuleEvaluator
from app.workflow_engine.application.state_management import WorkflowStateService
from app.workflow_engine.application.transition_management import WorkflowTransitionService
from app.workflow_engine.application.workflow_management import WorkflowService
from app.workflow_engine.infrastructure.boards_adapter import BoardsWorkflowContextAdapter
from app.workflow_engine.infrastructure.projects_adapter import ProjectsWorkflowContextAdapter
from app.workflow_engine.infrastructure.seed_data import WORKFLOW_PERMISSION_CATALOG
from app.workflow_engine.infrastructure.tasks_adapter import TasksWorkflowContextAdapter
from app.workflow_engine.infrastructure.unit_of_work import WorkflowEngineUnitOfWork
from app.workflow_engine.infrastructure.webhook_executor import HttpxWebhookExecutor
from app.workflow_engine.presentation import (
    deps,
    execution_router,
    states_router,
    transitions_router,
    workflows_router,
)

_logger = get_logger("workflow_engine.composition")
_AUTOMATION_SCAN_INTERVAL_SECONDS = 60.0


class WorkflowEngineModule:
    module_name = "workflow_engine"

    def __init__(
        self, settings: PlatformSettings, identity_module: IdentityModule, projects_module: ProjectsModule,
        tasks_module: TasksModule, boards_module: BoardsModule,
    ) -> None:
        self._settings = settings
        engine = create_async_engine(str(settings.database_url))
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

        self.dispatcher = EventDispatcher()
        self.notification_dispatcher = NotificationDispatcher()

        def uow_factory() -> WorkflowEngineUnitOfWork:
            return WorkflowEngineUnitOfWork(self._session_factory)

        self._uow_factory = uow_factory

        # --- Cross-context wiring (composition root only) ---
        permission_checker = identity_module.permission_evaluator
        project_context = ProjectsWorkflowContextAdapter(
            project_service=projects_module.project_service,
            project_membership_service=projects_module.project_membership_service,
        )
        tasks_context = TasksWorkflowContextAdapter(
            task_service=tasks_module.task_service, task_lifecycle_service=tasks_module.task_lifecycle_service,
            task_scheduling_service=tasks_module.task_scheduling_service,
            task_assignment_service=tasks_module.task_assignment_service, label_service=tasks_module.label_service,
        )
        boards_context = BoardsWorkflowContextAdapter(
            board_service=boards_module.board_service, card_movement_service=boards_module.card_movement_service,
        )
        user_directory = IdentityUserDirectoryAdapter(identity_module.create_unit_of_work)
        webhook_executor = HttpxWebhookExecutor()

        self.workflow_service = WorkflowService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.state_service = WorkflowStateService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )
        self.transition_service = WorkflowTransitionService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context,
        )

        rule_evaluator = RuleEvaluator(permission_checker=permission_checker, project_context=project_context)
        action_executor = ActionExecutor(
            tasks_context=tasks_context, notification_dispatcher=self.notification_dispatcher,
            user_directory=user_directory, webhook_executor=webhook_executor,
        )
        self.execution_service = WorkflowExecutionService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            project_context=project_context, tasks_context=tasks_context, boards_context=boards_context,
            rule_evaluator=rule_evaluator, action_executor=action_executor,
        )
        self.automation_service = WorkflowAutomationService(uow_factory=uow_factory, dispatcher=self.dispatcher, action_executor=action_executor)

        # --- Background Jobs (platform_core.jobs, reused from Tasks/Boards) ---
        self._job_executor = JobExecutor()
        self.job_scheduler = JobScheduler()
        self.job_scheduler.register(
            JobDefinition(name="workflow_engine_run_due_actions", func=self._run_due_actions, interval_seconds=_AUTOMATION_SCAN_INTERVAL_SECONDS)
        )

    async def _run_due_actions(self) -> None:
        processed = await self._job_executor.run("workflow_engine_run_due_actions", self.automation_service.run_due_actions)
        await _logger.ainfo("workflow_engine_run_due_actions_complete", processed_count=processed)

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(WorkflowService, self.workflow_service)
        container.register_instance(WorkflowStateService, self.state_service)
        container.register_instance(WorkflowTransitionService, self.transition_service)
        container.register_instance(WorkflowExecutionService, self.execution_service)
        container.register_instance(WorkflowAutomationService, self.automation_service)

    def mount(self, app: FastAPI) -> None:
        app.include_router(workflows_router.router)
        app.include_router(states_router.router)
        app.include_router(transitions_router.router)
        app.include_router(execution_router.router)

        app.dependency_overrides[deps.get_workflow_service] = lambda: self.workflow_service
        app.dependency_overrides[deps.get_workflow_state_service] = lambda: self.state_service
        app.dependency_overrides[deps.get_workflow_transition_service] = lambda: self.transition_service
        app.dependency_overrides[deps.get_workflow_execution_service] = lambda: self.execution_service


__all__ = ["WorkflowEngineModule", "WORKFLOW_PERMISSION_CATALOG"]
