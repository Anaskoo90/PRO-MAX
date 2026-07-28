import pytest

from app.boards.domain.entities import (
    Board,
    BoardCard,
    BoardColumn,
    EstimateType,
    Sprint,
    compute_position_between,
)
from app.boards.domain.exceptions import (
    BoardAlreadyArchivedError,
    BoardAlreadyDeletedError,
    BoardNotArchivedError,
    InvalidEstimateError,
    InvalidSprintDateRangeError,
    InvalidSprintTransitionError,
    InvalidWipLimitError,
)
from app.boards.domain.events import BoardArchived, BoardCreated
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7
from datetime import date, timedelta


def _new_board(**kwargs) -> Board:
    return Board.create(project_id=EntityId(new_uuid7()), org_id=OrgId(new_uuid7()), name="Demo Board", **kwargs)


def test_create_board_records_board_created_event() -> None:
    board = _new_board()
    events = board.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], BoardCreated)


def test_archive_then_restore_round_trips() -> None:
    board = _new_board()
    board.archive()
    assert board.status.value == "archived"
    assert board.archived_at is not None

    board.restore()
    assert board.status.value == "active"
    assert board.archived_at is None


def test_archiving_twice_raises() -> None:
    board = _new_board()
    board.archive()
    with pytest.raises(BoardAlreadyArchivedError):
        board.archive()


def test_restoring_a_non_archived_board_raises() -> None:
    board = _new_board()
    with pytest.raises(BoardNotArchivedError):
        board.restore()


def test_mark_deleted_twice_raises() -> None:
    board = _new_board()
    board.mark_deleted()
    with pytest.raises(BoardAlreadyDeletedError):
        board.mark_deleted()


def test_column_create_validates_positive_wip_limit() -> None:
    with pytest.raises(InvalidWipLimitError):
        BoardColumn.create(board_id=EntityId(new_uuid7()), name="Doing", position=1.0, wip_limit=0)


def test_column_set_wip_limit_rejects_non_positive() -> None:
    column = BoardColumn.create(board_id=EntityId(new_uuid7()), name="Doing", position=1.0)
    with pytest.raises(InvalidWipLimitError):
        column.set_wip_limit(-1)


def test_board_card_placement_and_backlog_detection() -> None:
    board_id = EntityId(new_uuid7())
    task_id = EntityId(new_uuid7())
    card = BoardCard.add_to_board(board_id=board_id, task_id=task_id)
    assert card.is_in_backlog() is True

    card.move_to_column(column_id=EntityId(new_uuid7()), position=5.0)
    assert card.is_in_backlog() is False
    assert card.position == 5.0


def test_board_card_set_estimate_story_points() -> None:
    card = BoardCard.add_to_board(board_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()))
    card.set_estimate(estimate_type=EstimateType.STORY_POINTS, value=5)
    assert card.estimate_type == EstimateType.STORY_POINTS
    assert card.estimate_value == 5


def test_board_card_set_estimate_rejects_negative_value() -> None:
    card = BoardCard.add_to_board(board_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()))
    with pytest.raises(InvalidEstimateError):
        card.set_estimate(estimate_type=EstimateType.HOURS, value=-1)


def test_board_card_custom_estimate_requires_label() -> None:
    card = BoardCard.add_to_board(board_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()))
    with pytest.raises(InvalidEstimateError):
        card.set_estimate(estimate_type=EstimateType.CUSTOM, value=3)


def test_sprint_create_validates_date_order() -> None:
    with pytest.raises(InvalidSprintDateRangeError):
        Sprint.create(
            board_id=EntityId(new_uuid7()), name="Sprint 1",
            start_date=date.today(), end_date=date.today() - timedelta(days=1),
        )


def test_sprint_lifecycle_transitions() -> None:
    sprint = Sprint.create(board_id=EntityId(new_uuid7()), name="Sprint 1")
    sprint.start()
    assert sprint.is_active() is True
    sprint.complete()
    assert sprint.status.value == "completed"


def test_sprint_invalid_transition_raises() -> None:
    sprint = Sprint.create(board_id=EntityId(new_uuid7()), name="Sprint 1")
    with pytest.raises(InvalidSprintTransitionError):
        sprint.complete()


def test_compute_position_between_inserts_correctly() -> None:
    first = compute_position_between(None, None)
    after_first = compute_position_between(first, None)
    between = compute_position_between(first, after_first)
    before_first = compute_position_between(None, first)

    assert first < between < after_first
    assert before_first < first
