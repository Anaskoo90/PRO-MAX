import pytest

from app.boards.application.board_management import BoardService
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary
from app.boards.domain.exceptions import BoardNotFoundError, InsufficientBoardPermissionError, ProjectNotAccessibleError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.boards.unit.fakes import AllowAllPermissionChecker, DenyAllPermissionChecker, FakeBoardsUnitOfWork, FakeProjectContext


def _make_service(uow, project_context, permission_checker=None) -> BoardService:
    return BoardService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(),
        permission_checker=permission_checker or AllowAllPermissionChecker(), project_context=project_context,
    )


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
    return uow, project_context, project_id, org_id, actor_id


@pytest.mark.asyncio
async def test_create_board_succeeds_for_a_project_member(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)

    board = await service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Sprint Board")

    assert board.name == "Sprint Board"
    assert board.board_type == "kanban"
    assert board.status == "active"


@pytest.mark.asyncio
async def test_create_board_rejects_mismatched_org_id(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    wrong_org_id = OrgId(new_uuid7())

    with pytest.raises(ProjectNotAccessibleError):
        await service.create_board(project_id=project_id, org_id=wrong_org_id, actor_user_id=actor_id, name="Demo")


@pytest.mark.asyncio
async def test_non_member_cannot_create_board(context) -> None:
    uow, project_context, project_id, org_id, _actor_id = context
    outsider_id = UserId(new_uuid7())
    service = _make_service(uow, project_context, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientBoardPermissionError):
        await service.create_board(project_id=project_id, org_id=org_id, actor_user_id=outsider_id, name="Demo")


@pytest.mark.asyncio
async def test_archive_restore_and_delete_round_trip(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    board = await service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    archived = await service.archive(board_id=board.id, actor_user_id=actor_id)
    assert archived.status == "archived"

    restored = await service.restore(board_id=board.id, actor_user_id=actor_id)
    assert restored.status == "active"

    await service.delete(board_id=board.id, actor_user_id=actor_id)
    # Soft-deleted boards are invisible to get_by_id (same convention as
    # every prior context), so a second delete 404s rather than raising
    # "already deleted".
    with pytest.raises(BoardNotFoundError):
        await service.delete(board_id=board.id, actor_user_id=actor_id)


@pytest.mark.asyncio
async def test_update_settings_merges_patch(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    board = await service.create_board(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    updated = await service.update_settings(board_id=board.id, actor_user_id=actor_id, patch={"color_scheme": "dark"})

    assert updated.settings["color_scheme"] == "dark"
