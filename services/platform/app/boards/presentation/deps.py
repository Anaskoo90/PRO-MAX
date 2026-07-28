"""
Shared FastAPI dependencies for the Boards & Agile Management presentation
layer.

Authentication is *not* reimplemented here — `get_current_user_claims` is
imported directly from app.identity.presentation.deps, same reuse pattern
every prior context has established (all contexts sit behind the same
FastAPI app and the same JwtTokenService instance).
"""

from __future__ import annotations

from app.identity.presentation.deps import get_current_user_claims  # noqa: F401  (re-exported for routers)
from app.boards.application.backlog_management import BacklogService
from app.boards.application.board_management import BoardService
from app.boards.application.card_movement import CardMovementService
from app.boards.application.column_management import ColumnService
from app.boards.application.estimate_management import EstimateService
from app.boards.application.sprint_management import SprintService
from app.boards.application.sprint_reporting import SprintReportingService
from app.boards.application.swimlane_management import SwimlaneService


def get_board_service() -> BoardService:
    raise NotImplementedError("BoardService dependency not wired")


def get_column_service() -> ColumnService:
    raise NotImplementedError("ColumnService dependency not wired")


def get_swimlane_service() -> SwimlaneService:
    raise NotImplementedError("SwimlaneService dependency not wired")


def get_card_movement_service() -> CardMovementService:
    raise NotImplementedError("CardMovementService dependency not wired")


def get_backlog_service() -> BacklogService:
    raise NotImplementedError("BacklogService dependency not wired")


def get_sprint_service() -> SprintService:
    raise NotImplementedError("SprintService dependency not wired")


def get_sprint_reporting_service() -> SprintReportingService:
    raise NotImplementedError("SprintReportingService dependency not wired")


def get_estimate_service() -> EstimateService:
    raise NotImplementedError("EstimateService dependency not wired")
