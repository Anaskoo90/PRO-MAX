import pytest

from app.boards.application.backlog_management import BacklogService
from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary, TaskSummary
from app.boards.application.sprint_management import SprintService
from app.boards.domain.exceptions import SprintNotFoundError
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
    sprint_service = SprintService(
        uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker,
        project_context=project_context, tasks_context=tasks_context,
    )
    backlog_service = BacklogService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    return board_service, card_service, sprint_service, backlog_service, project_id, org_id, actor_id, task_id


@pytest.mark.asyncio
async def test_new_card_appears_in_product_backlog(context) -> None:
    board_service, card_service, _ss, backlog_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    backlog = await backlog_service.list_product_backlog(board_id=board.id)

    assert len(backlog) == 1


@pytest.mark.asyncio
async def test_assign_to_sprint_moves_card_out_of_product_backlog(context) -> None:
    board_service, card_service, sprint_service, backlog_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    sprint = await sprint_service.create_sprint(board_id=board.id, actor_user_id=actor_id, name="Sprint 1")
    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    await backlog_service.assign_to_sprint(card_id=card.id, actor_user_id=actor_id, sprint_id=sprint.id)

    product_backlog = await backlog_service.list_product_backlog(board_id=board.id)
    sprint_backlog = await backlog_service.list_sprint_backlog(sprint_id=sprint.id)
    assert len(product_backlog) == 0
    assert len(sprint_backlog) == 1


@pytest.mark.asyncio
async def test_assign_to_sprint_from_another_board_is_rejected(context) -> None:
    board_service, card_service, sprint_service, backlog_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    other_board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Other")
    foreign_sprint = await sprint_service.create_sprint(board_id=other_board.id, actor_user_id=actor_id, name="Foreign Sprint")
    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    with pytest.raises(SprintNotFoundError):
        await backlog_service.assign_to_sprint(card_id=card.id, actor_user_id=actor_id, sprint_id=foreign_sprint.id)


@pytest.mark.asyncio
async def test_remove_from_sprint_returns_card_to_product_backlog(context) -> None:
    board_service, card_service, sprint_service, backlog_service, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    sprint = await sprint_service.create_sprint(board_id=board.id, actor_user_id=actor_id, name="Sprint 1")
    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)
    await backlog_service.assign_to_sprint(card_id=card.id, actor_user_id=actor_id, sprint_id=sprint.id)

    await backlog_service.remove_from_sprint(card_id=card.id, actor_user_id=actor_id)

    product_backlog = await backlog_service.list_product_backlog(board_id=board.id)
    assert len(product_backlog) == 1
