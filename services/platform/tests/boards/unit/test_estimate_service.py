import pytest

from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.boards.application.estimate_management import EstimateService
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary, TaskSummary
from app.boards.domain.entities import EstimateType
from app.boards.domain.exceptions import InvalidEstimateError
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
        tasks=[TaskSummary(id=task_id, project_id=project_id, org_id=org_id, title="Demo", status="backlog", priority="medium")]
    )
    dispatcher = EventDispatcher()
    permission_checker = AllowAllPermissionChecker()
    board_service = BoardService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    card_service = CardMovementService(
        uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker,
        project_context=project_context, tasks_context=tasks_context,
    )
    estimate_service = EstimateService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    return board_service, card_service, estimate_service, project_id, org_id, actor_id, task_id


@pytest.mark.asyncio
async def test_set_story_point_estimate(context) -> None:
    board_service, card_service, estimate_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    updated = await estimate_service.set_estimate(
        card_id=card.id, actor_user_id=actor_id, estimate_type=EstimateType.STORY_POINTS, value=8,
    )

    assert updated.estimate_type == "story_points"
    assert updated.estimate_value == 8


@pytest.mark.asyncio
async def test_custom_estimate_without_label_is_rejected(context) -> None:
    board_service, card_service, estimate_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    with pytest.raises(InvalidEstimateError):
        await estimate_service.set_estimate(card_id=card.id, actor_user_id=actor_id, estimate_type=EstimateType.CUSTOM, value=1)


@pytest.mark.asyncio
async def test_custom_estimate_with_label_succeeds(context) -> None:
    board_service, card_service, estimate_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    updated = await estimate_service.set_estimate(
        card_id=card.id, actor_user_id=actor_id, estimate_type=EstimateType.CUSTOM, value=1, custom_label="T-shirt: M",
    )

    assert updated.custom_estimate_label == "T-shirt: M"
