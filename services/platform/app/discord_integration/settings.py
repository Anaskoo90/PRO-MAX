"""
Discord Integration settings — extends PlatformSettings for the two values
this context needs beyond the base (per configuration/settings.py's own
documented extension pattern; PlatformSettings itself is untouched).

Constructed once in app/main.py, independently from the shared `settings`
object every other module receives, reading the same .env file.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, SecretStr, model_validator

from app.platform_core.configuration.settings import PlatformSettings


class DiscordIntegrationSettings(PlatformSettings):
    # Discord application/client id, used only to build the bot-invite URL
    # returned by request_setup_token. Defaulted (not required) so this
    # context constructs cleanly in any environment that hasn't configured
    # Discord yet — same "construct successfully with a dev default" spirit
    # as JwtTokenService's hardcoded dev signing key in identity/composition.py.
    discord_application_id: str = ""

    # Shared secret presented by the bot process on every call to the
    # bot-facing endpoints (presentation/bot_authentication.py) — the only
    # auth mechanism between the one trusted bot process and the backend;
    # see the Discord Setup Wizard design doc's Permission Model section.
    # Defaulted for the same reason as above; override via env in real
    # deployments. See platform_core.security.secrets_provider for the
    # real mechanism once a KMS vendor is chosen.
    discord_bot_service_secret: SecretStr = Field(
        default=SecretStr("dev-only-change-me"),
        min_length=1,
        validation_alias="GUILDDESK_SECRET_DISCORD_BOT_SERVICE_SECRET",
    )

    @model_validator(mode="after")
    def _validate_discord_production_constraints(self) -> Self:
        if not self.environment.is_production_like:
            return self

        bot_secret = self.discord_bot_service_secret.get_secret_value()
        if bot_secret == "dev-only-change-me" or len(bot_secret.strip()) < 32:
            raise ValueError(
                "GUILDDESK_SECRET_DISCORD_BOT_SERVICE_SECRET must contain at "
                "least 32 non-default characters in staging/production"
            )
        if self.discord_application_id.strip() in {"", "0"}:
            raise ValueError(
                "discord_application_id must be configured in staging/production"
            )
        return self
