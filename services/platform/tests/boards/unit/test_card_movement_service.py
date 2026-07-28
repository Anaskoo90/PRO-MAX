import pytest

from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.boards.application.column_management import ColumnService
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary, TaskStatusRejectedError, TaskSummary
from app.boards.domain.exceptions import TaskAlreadyOnBoardError, TaskNotAccessibleError, WipLimitExceededError
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
        tasks=[TaskSummary(id=task_id, project_id=project_id, org_id=org_id, title="Demo Task", status="backlog", priority="medium")]
    )
    dispatcher = EventDispatcher()
    permission_checker = AllowAllPermissionChecker()
    board_service = BoardService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    column_service = ColumnService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    card_service = CardMovementService(
        uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker,
        project_context=project_context, tasks_context=tasks_context,
    )
    return uow, board_service, column_service, card_service, tasks_context, project_id, org_id, actor_id, task_id


@pytest.mark.asyncio
async def test_add_task_to_board_places_it_in_backlog_by_default(context) -> None:
    _uow, board_service, _column_service, card_service, _tc, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    assert card.column_id is None


@pytest.mark.asyncio
async def test_adding_same_task_twice_is_rejected(context) -> None:
    _uow, board_service, _column_service, card_service, _tc, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    with pytest.raises(TaskAlreadyOnBoardError):
        await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)


@pytest.mark.asyncio
async def test_adding_a_task_from_another_project_is_rejected(context) -> None:
    _uow, board_service, _column_service, card_service, _tc, project_id, org_id, actor_id, _task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    foreign_task_id = EntityId(new_uuid7())

    with pytest.raises(TaskNotAccessibleError):
        await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=foreign_task_id)


@pytest.mark.asyncio
async def test_wip_limit_exceeded_blocks_move_into_column(context) -> None:
    _uow, board_service, column_service, card_service, tasks_context, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    column = await column_service.create_column(board_id=board.id, actor_user_id=actor_id, name="Doing", wip_limit=1)

    filler_task_id = EntityId(new_uuid7())
    tasks_context.tasks_by_id[filler_task_id] = TaskSummary(
        id=filler_task_id, project_id=project_id, org_id=org_id, title="Filler", status="backlog", priority="medium",
    )
    await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=filler_task_id, column_id=column.id)

    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)
    with pytest.raises(WipLimitExceededError):
        await card_service.move_task_to_column(card_id=card.id, actor_user_id=actor_id, column_id=column.id)


@pytest.mark.asyncio
async def test_move_into_mapped_column_syncs_task_status(context) -> None:
    _uow, board_service, column_service, card_service, tasks_context, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    column = await column_service.create_column(
        board_id=board.id, actor_user_id=actor_id, name="Done", mapped_task_status="done",
    )
    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    await card_service.move_task_to_column(card_id=card.id, actor_user_id=actor_id, column_id=column.id)

    assert (task_id, "done") in tasks_context.status_changes


@pytest.mark.asyncio
async def test_move_into_mapped_column_propagates_rejected_status(context) -> None:
    _uow, board_service, column_service, card_service, tasks_context, project_id, org_id, actor_id, task_id = context
    tasks_context._reject_statuses.add("done")
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    column = await column_service.create_column(
        board_id=board.id, actor_user_id=actor_id, name="Done", mapped_task_status="done",
    )
    card = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id)

    with pytest.raises(TaskStatusRejectedError):
        await card_service.move_task_to_column(card_id=card.id, actor_user_id=actor_id, column_id=column.id)


@pytest.mark.asyncio
async def test_reorder_task_keeps_ordering_consistent(context) -> None:
    _uow, board_service, column_service, card_service, tasks_context, project_id, org_id, actor_id, task_id = context
    board = await board_service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    column = await column_service.create_column(board_id=board.id, actor_user_id=actor_id, name="Doing")

    second_task_id = EntityId(new_uuid7())
    tasks_context.tasks_by_id[second_task_id] = TaskSummary(
        id=second_task_id, project_id=project_id, org_id=org_id, title="Second", status="backlog", priority="medium",
    )
    first = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=task_id, column_id=column.id)
    second = await card_service.add_task_to_board(board_id=board.id, actor_user_id=actor_id, task_id=second_task_id, column_id=column.id)
    assert first.position < second.position

    reordered_first = await card_service.reorder_task(
        card_id=first.id, actor_user_id=actor_id, previous_card_id=second.id, next_card_id=None,
    )
    assert reordered_first.position > second.position
