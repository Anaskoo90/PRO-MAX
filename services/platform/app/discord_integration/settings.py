"""
Discord Integration settings — extends PlatformSettings for the two values
this context needs beyond the base (per configuration/settings.py's own
documented extension pattern; PlatformSettings itself is untouched).

Constructed once in app/main.py, independently from the shared `settings`
object every other module receives, reading the same .env file.
"""

from __future__ import annotations

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
    discord_bot_service_secret: str = "dev-only-change-me"
