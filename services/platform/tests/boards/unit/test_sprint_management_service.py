import pytest

from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary, TaskSummary
from app.boards.application.sprint_management import SprintService
from app.boards.domain.entities import EstimateType
from app.boards.domain.exceptions import OnlyOneActiveSprintPerBoardError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.boards.unit.fakes import AllowAllPermissionChecker, FakeBoardsUnitOfWork, FakeProjectContext, FakeTasksContext


@pytest.fixture
def context():
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    actor_id = UserId(new_uuid7())
    uow = FakeBoardsUnitOfWork()
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=org_id, workspace_id=new_uuid7(), status="active"),
        members=[ProjectMemberSummary(user_id=actor_id, role="owner", status="active")],
    )
    tasks_context = FakeTasksContext()
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
    return uow, board_service, card_service, sprint_service, tasks_context, project_id, org_id, actor_id


@pytest.mark.asyncio
async def test_start_complete_and_cancel_lifecycle(context) -> None:
    _uow, board_service, _cs, sprint_service, _tc, project_id, org_id, actor_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    sprint = await sprint_service.create_sprint(board_id=board.id, actor_user_id=actor_id, name="Sprint 1")

    started = await sprint_service.start_sprint(sprint_id=sprint.id, actor_user_id=actor_id)
    assert started.status == "active"

    completed = await sprint_service.complete_sprint(sprint_id=sprint.id, actor_user_id=actor_id)
    assert completed.status == "completed"


@pytest.mark.asyncio
async def test_only_one_active_sprint_per_board(context) -> None:
    _uow, board_service, _cs, sprint_service, _tc, project_id, org_id, actor_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    first = await sprint_service.create_sprint(board_id=board.id, actor_user_id=actor_id, name="Sprint 1")
    second = await sprint_service.create_sprint(board_id=board.id, actor_user_id=actor_id, name="Sprint 2")
    await sprint_service.start_sprint(sprint_id=first.id, actor_user_id=actor_id)

    with pytest.raises(OnlyOneActiveSprintPerBoardError):
        await sprint_service.start_sprint(sprint_id=second.id, actor_user_id=actor_id)


@pytest.mark.asyncio
async def test_cancel_sprint(context) -> None:
    _uow, board_service, _cs, sprint_service, _tc, project_id, org_id, actor_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    sprint = await sprint_service.create_sprint(board_id=board.id, actor_user_id=actor_id, name="Sprint 1")

    cancelled = await sprint_service.cancel_sprint(sprint_id=sprint.id, actor_user_id=actor_id)
    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_velocity_counts_only_done_story_point_cards(context) -> None:
    uow, board_service, card_service, sprint_service, tasks_context, project_id, org_id, actor_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    sprint = await sprint_service.create_sprint(board_id=board.id, actor_user_id=actor_id, name="Sprint 1")

    done_task_id = EntityId(new_uuid7())
    not_done_task_id = EntityId(new_uuid7())
    tasks_context.tasks_by_id[done_task_id] = TaskSummary(id=done_task_id, project_id=project_id, org_id=org_id, title="Done Task", status="done", priority="medium")
    tasks_context.tasks_by_id[not_done_task_id] = TaskSummary(id=not_done_task_id, project_id=project_id, org_id=org_id, title="In Progress", status="in_progress", priority="medium")

    done_card_dto = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=done_task_id)
    not_done_card_dto = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=not_done_task_id)
    done_card = await uow.board_cards.get_by_id(done_card_dto.id)
    done_card.assign_to_sprint(sprint.id)
    done_card.set_estimate(estimate_type=EstimateType.STORY_POINTS, value=5)
    await uow.board_cards.update(done_card)
    not_done_card = await uow.board_cards.get_by_id(not_done_card_dto.id)
    not_done_card.assign_to_sprint(sprint.id)
    not_done_card.set_estimate(estimate_type=EstimateType.STORY_POINTS, value=3)
    await uow.board_cards.update(not_done_card)

    velocity = await sprint_service.get_velocity(sprint_id=sprint.id)

    assert velocity == 5
