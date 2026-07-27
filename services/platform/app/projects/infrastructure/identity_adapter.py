"""
Anti-Corruption Layer: the only file in this bounded context permitted to
import Identity's infrastructure types. Translates Identity's User entity
into this context's own UserSummary (application.ports.UserSummary) so
nothing above the infrastructure layer here ever sees an Identity type.

Constructed in composition.py with a reference to IdentityModule's own
`create_unit_of_work` factory — same database, same transaction-per-call
convention, just a different bounded context's tables.
"""

from __future__ import annotations

from typing import Callable
from uuid import UUID

from app.identity.infrastructure.unit_of_work import IdentityUnitOfWork
from app.projects.application.ports import UserSummary


class IdentityUserDirectoryAdapter:
    def __init__(self, identity_uow_factory: Callable[[], IdentityUnitOfWork]) -> None:
        self._identity_uow_factory = identity_uow_factory

    async def find_by_email(self, *, org_id: UUID, email: str) -> UserSummary | None:
        async with self._identity_uow_factory() as uow:
            user = await uow.users.get_by_email(org_id, email.strip().lower())
        if user is None:
            return None
        return UserSummary(id=user.id, email=str(user.email), display_name=user.display_name)

    async def get_by_id(self, *, user_id: UUID) -> UserSummary | None:
        async with self._identity_uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
        if user is None:
            return None
        return UserSummary(id=user.id, email=str(user.email), display_name=user.display_name)
