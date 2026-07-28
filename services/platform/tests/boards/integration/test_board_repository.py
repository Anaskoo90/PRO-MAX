import pytest

from app.boards.domain.entities import Board, BoardColumn, Sprint
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def test_add_then_get_by_id_round_trips(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    board = Board.create(project_id=project_id, org_id=org_id, name="Demo Board")
    await uow.boards.add(board)
    await uow.session.flush()

    fetched = await uow.boards.get_by_id(board.id)

    assert fetched is not None
    assert fetched.name == "Demo Board"
    assert fetched.project_id == project_id


async def test_update_persists_archive_and_bumps_version(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    board = Board.create(project_id=project_id, org_id=org_id, name="Demo Board")
    await uow.boards.add(board)
    await uow.session.flush()

    board.archive()
    await uow.boards.update(board)
    await uow.session.flush()

    fetched = await uow.boards.get_by_id(board.id)
    assert fetched.status.value == "archived"
    assert fetched.version == 2


async def test_list_for_project_excludes_archived_by_default(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    active_board = Board.create(project_id=project_id, org_id=org_id, name="Active")
    archived_board = Board.create(project_id=project_id, org_id=org_id, name="Archived")
    archived_board.archive()
    await uow.boards.add(active_board)
    await uow.boards.add(archived_board)
    await uow.session.flush()

    visible = await uow.boards.list_for_project(project_id)
    visible_ids = {b.id for b in visible}

    assert active_board.id in visible_ids
    assert archived_board.id not in visible_ids


async def test_column_wip_limit_and_position_round_trip(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    board = Board.create(project_id=project_id, org_id=org_id, name="Demo Board")
    await uow.boards.add(board)
    await uow.session.flush()

    column = BoardColumn.create(board_id=board.id, name="Doing", position=1024.0, wip_limit=3)
    await uow.board_columns.add(column)
    await uow.session.flush()

    fetched = await uow.board_columns.get_by_id(column.id)
    assert fetched is not None
    assert fetched.wip_limit == 3
    assert fetched.position == 1024.0


async def test_sprint_get_active_for_board(uow) -> None:
    project_id = EntityId(new_uuid7())
    org_id = OrgId(new_uuid7())
    board = Board.create(project_id=project_id, org_id=org_id, name="Demo Board")
    await uow.boards.add(board)
    await uow.session.flush()

    sprint = Sprint.create(board_id=board.id, name="Sprint 1")
    await uow.sprints.add(sprint)
    await uow.session.flush()

    assert await uow.sprints.get_active_for_board(board.id) is None

    sprint.start()
    await uow.sprints.update(sprint)
    await uow.session.flush()

    active = await uow.sprints.get_active_for_board(board.id)
    assert active is not None
    assert active.id == sprint.id
