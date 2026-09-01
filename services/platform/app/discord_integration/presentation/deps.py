"""
Shared FastAPI dependencies for the Discord Integration presentation layer.

Every `get_*` function below is a placeholder resolved by composition.py
via `app.dependency_overrides` — routers depend on these functions, never
on a concrete service instance, so the presentation layer has no
construction-order dependency on composition.py.

Authentication is *not* reimplemented here — `get_current_user_claims` is
imported directly from app.identity.presentation.deps, same reuse pattern
every prior context has established (all contexts sit behind the same
FastAPI app and the same JwtTokenService instance).
"""

from __future__ import annotations

from app.identity.presentation.deps import get_current_user_claims  # noqa: F401  (re-exported for routers)
from app.discord_integration.application.discord_setup import DiscordSetupService


def get_discord_setup_service() -> DiscordSetupService:
    raise NotImplementedError("DiscordSetupService dependency not wired")


def get_bot_service_secret() -> str:
    raise NotImplementedError("bot service secret dependency not wired")
