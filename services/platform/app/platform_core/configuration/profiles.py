from __future__ import annotations

from enum import StrEnum


class EnvironmentProfile(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"

    @property
    def is_production_like(self) -> bool:
        return self in (EnvironmentProfile.STAGING, EnvironmentProfile.PRODUCTION)
