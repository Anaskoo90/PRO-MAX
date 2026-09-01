"""
Shared FastAPI dependencies for the Ticket System presentation layer.

Every `get_*` function below is a placeholder resolved by composition.py
via `app.dependency_overrides` — routers depend on these functions, never
on a concrete service instance, so the presentation layer has no
construction-order dependency on composition.py.

Authentication is *not* reimplemented here:
- `get_current_user_claims` is imported directly from
  app.identity.presentation.deps, same reuse pattern every prior context
  has established.
- `require_bot_service_secret` is imported directly from
  app.discord_integration.presentation.bot_authentication — there is one
  bot process and one shared secret for every bot-facing endpoint across
  every bounded context, not a per-context secret, so this is reused as-is
  rather than reimplemented here.
"""

from __future__ import annotations

from app.discord_integration.presentation.bot_authentication import require_bot_service_secret  # noqa: F401
from app.identity.presentation.deps import get_current_user_claims  # noqa: F401  (re-exported for routers)
from app.ticket_system.application.ticket_categories import TicketCategoryService
from app.ticket_system.application.ticket_lifecycle import TicketLifecycleService


def get_ticket_lifecycle_service() -> TicketLifecycleService:
    raise NotImplementedError("TicketLifecycleService dependency not wired")


def get_ticket_category_service() -> TicketCategoryService:
    raise NotImplementedError("TicketCategoryService dependency not wired")
