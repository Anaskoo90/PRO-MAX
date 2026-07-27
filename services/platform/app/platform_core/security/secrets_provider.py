"""
Secret Providers: the abstraction the still-undecided KMS vendor choice
(standing gap, Enterprise Security Architecture) will implement. Local dev
and CI use the env-backed provider; a real KMS-backed provider slots in
behind the same Protocol with no caller change.
"""

from __future__ import annotations

import os
from typing import Protocol


class SecretNotFoundError(Exception):
    def __init__(self, secret_name: str) -> None:
        super().__init__(f"Secret '{secret_name}' was not found")


class SecretProvider(Protocol):
    async def get_secret(self, name: str) -> str: ...


class EnvironmentSecretProvider:
    """Local dev / CI only — reads GUILDDESK_SECRET_<NAME> env vars.
    Never used in staging/production (see PlatformSettings' production
    validation, which should be extended to reject this provider once a
    KMS vendor is selected)."""

    async def get_secret(self, name: str) -> str:
        env_key = f"GUILDDESK_SECRET_{name.upper()}"
        value = os.environ.get(env_key)
        if value is None:
            raise SecretNotFoundError(name)
        return value
