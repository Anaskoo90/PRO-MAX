"""SMS Provider Interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SmsMessage:
    to_phone_number: str
    body: str


class SmsSendError(Exception):
    pass


class SmsProvider(Protocol):
    async def send(self, message: SmsMessage) -> None: ...
