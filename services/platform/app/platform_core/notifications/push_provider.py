"""Push Provider Interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class PushMessage:
    device_token: str
    title: str
    body: str
    data: dict[str, Any] | None = None


class PushSendError(Exception):
    pass


class PushProvider(Protocol):
    async def send(self, message: PushMessage) -> None: ...
