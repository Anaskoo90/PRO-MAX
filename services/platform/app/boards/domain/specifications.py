"""Boards & Agile Management specifications, per the Domain Modeling & DDD
Blueprint's Specification pattern (shared_kernel.validation.Specification)."""

from __future__ import annotations

from app.platform_core.shared_kernel.validation import Specification
from app.boards.domain.entities import Sprint, SprintStatus


class SprintIsActiveSpecification(Specification[Sprint]):
    def is_satisfied_by(self, candidate: Sprint) -> bool:
        return candidate.status == SprintStatus.ACTIVE


class WipLimitRespectedSpecification(Specification[tuple[int | None, int]]):
    """Candidate is (wip_limit, current_card_count)."""

    def is_satisfied_by(self, candidate: tuple[int | None, int]) -> bool:
        wip_limit, current_count = candidate
        return wip_limit is None or current_count < wip_limit
