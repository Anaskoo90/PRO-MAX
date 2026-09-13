"""Email provider port and the SMTP adapter used by the composition root."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeEmailMessage
from email.utils import formataddr
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


class SmtpEmailProvider:
    """Send transactional email through any standards-compliant SMTP server.

    The blocking standard-library client runs in a worker thread so SMTP
    handshakes and delivery never block FastAPI's event loop.  Both implicit
    TLS (normally port 465) and STARTTLS (normally port 587) are supported.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_address: str,
        from_name: str = "GuildDesk",
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool = False,
        start_tls: bool = False,
        timeout_seconds: float = 10.0,
    ) -> None:
        if use_ssl and start_tls:
            raise ValueError("SMTP implicit TLS and STARTTLS cannot both be enabled")
        if (username is None) != (password is None):
            raise ValueError("SMTP username and password must be configured together")

        self._host = host
        self._port = port
        self._from_address = from_address
        self._from_name = from_name
        self._username = username
        self._password = password
        self._use_ssl = use_ssl
        self._start_tls = start_tls
        self._timeout_seconds = timeout_seconds

    async def send(self, message: EmailMessage) -> None:
        try:
            mime_message = self._build_message(message)
            await asyncio.to_thread(self._send_sync, mime_message)
        except (OSError, smtplib.SMTPException, ValueError) as exc:
            raise EmailSendError(f"SMTP delivery to '{message.to_address}' failed") from exc

    def _build_message(self, message: EmailMessage) -> MimeEmailMessage:
        mime_message = MimeEmailMessage()
        mime_message["From"] = formataddr((self._from_name, self._from_address))
        mime_message["To"] = message.to_address
        mime_message["Subject"] = message.subject
        mime_message.set_content(message.text_body or message.html_body)
        mime_message.add_alternative(message.html_body, subtype="html")
        return mime_message

    def _send_sync(self, message: MimeEmailMessage) -> None:
        if self._use_ssl:
            smtp_client = smtplib.SMTP_SSL(
                self._host,
                self._port,
                timeout=self._timeout_seconds,
                context=ssl.create_default_context(),
            )
        else:
            smtp_client = smtplib.SMTP(
                self._host,
                self._port,
                timeout=self._timeout_seconds,
            )

        with smtp_client as client:
            client.ehlo()
            if self._start_tls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if self._username is not None:
                client.login(self._username, self._password or "")
            client.send_message(message)
