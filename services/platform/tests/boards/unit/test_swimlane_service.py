import pytest

from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary, TaskSummary
from app.boards.application.swimlane_management import SwimlaneService
from app.boards.domain.entities import SwimlaneStrategy
from app.boards.domain.exceptions import CustomSwimlaneRequiredError
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
        tasks=[TaskSummary(id=task_id, project_id=project_id, org_id=org_id, title="Demo", status="backlog", priority="high")]
    )
    dispatcher = EventDispatcher()
    permission_checker = AllowAllPermissionChecker()
    board_service = BoardService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    card_service = CardMovementService(
        uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker,
        project_context=project_context, tasks_context=tasks_context,
    )
    swimlane_service = SwimlaneService(
        uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker,
        project_context=project_context, tasks_context=tasks_context,
    )
    return board_service, card_service, swimlane_service, project_id, org_id, actor_id, task_id


@pytest.mark.asyncio
async def test_custom_swimlane_requires_custom_strategy(context) -> None:
    board_service, _cs, swimlane_service, project_id, org_id, actor_id, _task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    with pytest.raises(CustomSwimlaneRequiredError):
        await swimlane_service.create_swimlane(board_id=board.id, actor_user_id=actor_id, name="Backend")


@pytest.mark.asyncio
async def test_custom_swimlane_created_when_strategy_is_custom(context) -> None:
    board_service, _cs, swimlane_service, project_id, org_id, actor_id, _task_id = context
    board = await board_service.create_board(
        project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo", swimlane_strategy=SwimlaneStrategy.CUSTOM,
    )

    swimlane = await swimlane_service.create_swimlane(board_id=board.id, actor_user_id=actor_id, name="Backend")

    assert swimlane.name == "Backend"


@pytest.mark.asyncio
async def test_epic_strategy_returns_honest_placeholder_group(context) -> None:
    """EPIC is a valid enum value but the platform has no Epic concept
    anywhere yet — the service must not fabricate epic-based groups."""
    board_service, card_service, swimlane_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(
        project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo", swimlane_strategy=SwimlaneStrategy.EPIC,
    )
    await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    groups = await swimlane_service.compute_dynamic_groups(board_id=board.id)

    assert len(groups) == 1
    assert groups[0].label == "No epics available"
    assert len(groups[0].card_ids) == 1


@pytest.mark.asyncio
async def test_priority_strategy_groups_cards_by_task_priority(context) -> None:
    board_service, card_service, swimlane_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(
        project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo", swimlane_strategy=SwimlaneStrategy.PRIORITY,
    )
    await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    groups = await swimlane_service.compute_dynamic_groups(board_id=board.id)

    assert len(groups) == 1
    assert groups[0].key == "high"
