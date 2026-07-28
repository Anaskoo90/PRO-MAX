import pytest

from app.boards.application.board_management import BoardService
from app.boards.application.column_management import ColumnService
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary
from app.boards.domain.exceptions import ColumnNameAlreadyExistsError, InvalidColumnColorError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.boards.unit.fakes import AllowAllPermissionChecker, FakeBoardsUnitOfWork, FakeProjectContext


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
    dispatcher = EventDispatcher()
    permission_checker = AllowAllPermissionChecker()
    board_service = BoardService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    column_service = ColumnService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    return uow, board_service, column_service, project_id, org_id, actor_id


@pytest.mark.asyncio
async def test_create_column_computes_incrementing_positions(context) -> None:
    _uow, board_service, column_service, project_id, org_id, actor_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    todo = await column_service.create_column(board_id=board.id, actor_user_id=actor_id, name="To Do")
    doing = await column_service.create_column(board_id=board.id, actor_user_id=actor_id, name="Doing")

    assert todo.position < doing.position


@pytest.mark.asyncio
async def test_duplicate_column_name_on_same_board_rejected(context) -> None:
    _uow, board_service, column_service, project_id, org_id, actor_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    await column_service.create_column(board_id=board.id, actor_user_id=actor_id, name="To Do")

    with pytest.raises(ColumnNameAlreadyExistsError):
        await column_service.create_column(board_id=board.id, actor_user_id=actor_id, name="To Do")


@pytest.mark.asyncio
async def test_create_column_rejects_invalid_color(context) -> None:
    _uow, board_service, column_service, project_id, org_id, actor_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    with pytest.raises(InvalidColumnColorError):
        await column_service.create_column(board_id=board.id, actor_user_id=actor_id, name="To Do", color="not-a-color")


@pytest.mark.asyncio
async def test_delete_column_moves_orphaned_cards_back_to_backlog(context) -> None:
    uow, board_service, column_service, project_id, org_id, actor_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    column = await column_service.create_column(board_id=board.id, actor_user_id=actor_id, name="To Do")

    from app.boards.domain.entities import BoardCard
    card = BoardCard.add_to_board(board_id=board.id, task_id=EntityId(new_uuid7()), column_id=column.id, position=1.0)
    await uow.board_cards.add(card)

    await column_service.delete_column(column_id=column.id, actor_user_id=actor_id)

    refreshed = await uow.board_cards.get_by_id(card.id)
    assert refreshed.column_id is None
