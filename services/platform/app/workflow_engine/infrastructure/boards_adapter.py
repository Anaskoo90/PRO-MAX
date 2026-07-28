"""
Anti-Corruption Layer: the only file in this bounded context permitted to
depend on Boards & Agile Management. Wraps Boards' own public application
services (BoardService, CardMovementService — never Boards' infrastructure)
to answer "which board/sprint (if any) is this task currently placed on",
the data the BOARD and SPRINT workflow conditions need.

Boards does not expose a "find the card for this task_id" query across an
entire project (its repositories are scoped by board_id/column_id/sprint_id
plus a per-board get_by_task), so this iterates the project's boards and
each board's cards via existing public methods — O(boards x cards) per
lookup. That is an honest, composition-only reuse of what Boards already
exposes rather than a fabricated shortcut; a future turn could ask Boards
to add a dedicated cross-board lookup if this becomes a hot path.
"""

from __future__ import annotations

from uuid import UUID

from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.workflow_engine.application.ports import BoardPlacementSummary


class BoardsWorkflowContextAdapter:
    def __init__(self, *, board_service: BoardService, card_movement_service: CardMovementService) -> None:
        self._board_service = board_service
        self._card_movement_service = card_movement_service

    async def get_board_placement_for_task(self, *, project_id: UUID, task_id: UUID) -> BoardPlacementSummary | None:
        boards = await self._board_service.list_for_project(project_id=project_id, include_archived=True)
        for board in boards:
            cards = await self._card_movement_service.list_for_board(board_id=board.id)
            match = next((c for c in cards if c.task_id == task_id), None)
            if match is not None:
                return BoardPlacementSummary(board_id=board.id, column_id=match.column_id, sprint_id=match.sprint_id)
        return None
