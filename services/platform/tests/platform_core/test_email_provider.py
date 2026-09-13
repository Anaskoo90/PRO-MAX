import smtplib
from email.message import EmailMessage as MimeEmailMessage

import pytest
from app.platform_core.notifications.email_provider import (
    EmailMessage,
    EmailSendError,
    SmtpEmailProvider,
)


class _FakeSmtpClient:
    def __init__(self) -> None:
        self.ehlo_count = 0
        self.started_tls = False
        self.login_credentials: tuple[str, str] | None = None
        self.message: MimeEmailMessage | None = None

    def __enter__(self) -> "_FakeSmtpClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        return None

    def ehlo(self) -> None:
        self.ehlo_count += 1

    def starttls(self, *, context) -> None:  # noqa: ANN001
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_credentials = (username, password)

    def send_message(self, message: MimeEmailMessage) -> None:
        self.message = message


@pytest.mark.asyncio
async def test_smtp_provider_delivers_multipart_email_with_starttls_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeSmtpClient()
    monkeypatch.setattr(smtplib, "SMTP", lambda *args, **kwargs: client)
    provider = SmtpEmailProvider(
        host="smtp.example.com",
        port=587,
        from_address="no-reply@example.com",
        from_name="GuildDesk",
        username="smtp-user",
        password="smtp-password",
        start_tls=True,
    )

    await provider.send(
        EmailMessage(
            to_address="member@example.com",
            subject="Verify your email",
            html_body="<p>Open the verification link</p>",
            text_body="Open the verification link",
        )
    )

    assert client.ehlo_count == 2
    assert client.started_tls is True
    assert client.login_credentials == ("smtp-user", "smtp-password")
    assert client.message is not None
    assert client.message["From"] == "GuildDesk <no-reply@example.com>"
    assert client.message["To"] == "member@example.com"
    assert client.message["Subject"] == "Verify your email"
    assert client.message.is_multipart()


@pytest.mark.asyncio
async def test_smtp_provider_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_to_connect(*args, **kwargs):  # noqa: ANN002, ANN003
        raise smtplib.SMTPConnectError(421, "unavailable")

    monkeypatch.setattr(smtplib, "SMTP", fail_to_connect)
    provider = SmtpEmailProvider(
        host="smtp.example.com",
        port=25,
        from_address="no-reply@example.com",
    )

    with pytest.raises(EmailSendError):
        await provider.send(
            EmailMessage(
                to_address="member@example.com",
                subject="Hello",
                html_body="Hello",
            )
        )


def test_smtp_provider_rejects_conflicting_tls_modes() -> None:
    with pytest.raises(ValueError, match="cannot both be enabled"):
        SmtpEmailProvider(
            host="smtp.example.com",
            port=465,
            from_address="no-reply@example.com",
            use_ssl=True,
            start_tls=True,
        )
