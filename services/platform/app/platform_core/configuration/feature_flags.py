"""
Feature Flags: a provider Protocol plus a static (env/config-backed)
implementation. This is the extension point the future GrowthBook/LaunchDarkly
integration (still unselected — vendor undecided, per the standing gap
tracked since the Solution Design Pack extension) would implement; nothing
in the application layer should import a vendor SDK directly, only this
Protocol.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class FeatureFlagProvider(Protocol):
    async def is_enabled(
        self, flag_key: str, *, org_id: UUID | None = None, default: bool = False
    ) -> bool: ...


class StaticFeatureFlagProvider:
    """In-memory/env-backed provider for local dev and tests."""

    def __init__(self, flags: dict[str, bool] | None = None) -> None:
        self._flags = flags or {}

    async def is_enabled(
        self, flag_key: str, *, org_id: UUID | None = None, default: bool = False
    ) -> bool:
        return self._flags.get(flag_key, default)

    def set(self, flag_key: str, enabled: bool) -> None:
        self._flags[flag_key] = enabled
