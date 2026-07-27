"""Email Provider Interface: implemented by whichever transactional-email
vendor is selected (not decided in platform_core — this is a Notification
Center integration-provider concern, per the Integration Layer pattern)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to_address: str
    subject: str
    html_body: str
    text_body: str | None = None


class EmailSendError(Exception):
    pass


class EmailProvider(Protocol):
    async def send(self, message: EmailMessage) -> None: ...
