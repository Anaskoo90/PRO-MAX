from datetime import date, timedelta

import pytest

from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary, TaskSummary
from app.boards.application.sprint_management import SprintService
from app.boards.application.sprint_reporting import SprintReportingService
from app.boards.domain.entities import EstimateType
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.boards.unit.fakes import AllowAllPermissionChecker, FakeBoardsUnitOfWork, FakeProjectContext, FakeTasksContext


@pytest.fixture
def context():
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    actor_id = UserId(new_uuid7())
    task_id = EntityId(new_uuid7())
    uow = FakeBoardsUnitOfWork()
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=org_id, workspace_id=new_uuid7(), status="active"),
        members=[ProjectMemberSummary(user_id=actor_id, role="owner", status="active")],
    )
    tasks_context = FakeTasksContext(
        tasks=[TaskSummary(id=task_id, project_id=project_id, org_id=org_id, title="Demo", status="in_progress", priority="medium")]
    )
    dispatcher = EventDispatcher()
    permission_checker = AllowAllPermissionChecker()
    board_service = BoardService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    card_service = CardMovementService(
        uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker,
        project_context=project_context, tasks_context=tasks_context,
    )
    sprint_service = SprintService(
        uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker,
        project_context=project_context, tasks_context=tasks_context,
    )
    reporting_service = SprintReportingService(uow_factory=lambda: uow, tasks_context=tasks_context)
    return uow, board_service, card_service, sprint_service, reporting_service, project_id, org_id, actor_id, task_id


@pytest.mark.asyncio
async def test_record_daily_snapshots_is_idempotent_per_day(context) -> None:
    uow, board_service, card_service, sprint_service, reporting_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    sprint = await sprint_service.create_sprint(
        board_id=board.id, actor_user_id=actor_id, name="Sprint 1",
        start_date=date.today(), end_date=date.today() + timedelta(days=10), capacity=10,
    )
    await sprint_service.start_sprint(sprint_id=sprint.id, actor_user_id=actor_id)
    card_dto = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)
    card = await uow.board_cards.get_by_id(card_dto.id)
    card.assign_to_sprint(sprint.id)
    card.set_estimate(estimate_type=EstimateType.STORY_POINTS, value=5)
    await uow.board_cards.update(card)

    written_first = await reporting_service.record_daily_snapshots()
    written_second = await reporting_service.record_daily_snapshots()

    assert written_first == 1
    assert written_second == 0


@pytest.mark.asyncio
async def test_burndown_report_includes_ideal_line(context) -> None:
    _uow, board_service, _card_service, sprint_service, reporting_service, project_id, org_id, actor_id, _task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    sprint = await sprint_service.create_sprint(
        board_id=board.id, actor_user_id=actor_id, name="Sprint 1",
        start_date=date.today(), end_date=date.today() + timedelta(days=5), capacity=20,
    )

    report = await reporting_service.get_burndown(sprint_id=sprint.id)

    assert report.capacity == 20
    assert len(report.ideal_remaining_by_day) == 6
    assert report.ideal_remaining_by_day[0] == 20
    assert report.ideal_remaining_by_day[-1] == 0
