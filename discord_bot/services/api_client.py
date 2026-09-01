"""
Thin async HTTP client for the GuildDesk platform API.

This is the *only* file allowed to know the shape of the backend's HTTP
responses — cogs never call httpx directly, they call methods on
ApiClient, exactly the same boundary discipline the backend itself uses
for its own Anti-Corruption Layers between bounded contexts.

One instance is constructed for the lifetime of the bot process (see
client.py) and reused across every command invocation, rather than opening
a new connection per interaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True, slots=True)
class TicketData:
    id: str
    ticket_number: int
    discord_channel_id: str
    title: str
    status: str
    claimed_by_discord_user_id: str | None


@dataclass(frozen=True, slots=True)
class TicketResult:
    ok: bool
    ticket: TicketData | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class TicketCategoryData:
    id: str
    name: str
    discord_category_channel_id: str
    staff_discord_role_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TicketCategoriesResult:
    ok: bool
    categories: list[TicketCategoryData] = field(default_factory=list)
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class TicketCategoryResult:
    ok: bool
    category: TicketCategoryData | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class DiscordSetupResult:
    """Outcome of completing the setup wizard for one Discord guild —
    `ok=False` covers every failure mode (invalid/expired/already-used
    code, guild already linked elsewhere, network/transport error) with a
    single `error_message` a command handler can show as-is."""

    ok: bool
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class GuildStatusResult:
    ok: bool
    linked: bool = False
    org_name: str | None = None
    discord_guild_name: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class UnlinkResult:
    ok: bool
    error_message: str | None = None


class ApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        bot_service_secret: str = "",
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # transport is exposed only so tests can substitute httpx.MockTransport
        # instead of making real network calls; production code never passes it.
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds, transport=transport)
        self._bot_headers = {"X-GuildDesk-Bot-Secret": bot_service_secret}

    async def check_health(self) -> bool:
        """GET /health — the platform's dependency-level health report
        (see app/main.py). That endpoint always answers 200 even when a
        dependency is down; it reports per-check status inside the body
        (`{"checks": [{"status": "healthy" | "degraded" | "unhealthy", ...}]}`),
        never via the HTTP status code — so a real health determination
        has to look at the body, not just "did we get a response".
        Any transport failure, non-2xx response, or unparseable body is
        treated as "unhealthy" rather than raised: a Discord command
        handler needs a clean boolean to render a status message, not an
        exception to catch at every call site."""
        try:
            response = await self._http.get("/health")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return False
        checks = payload.get("checks", [])
        return len(checks) > 0 and all(check.get("status") == "healthy" for check in checks)

    def _error_message(self, response: httpx.Response) -> str:
        """Best-effort extraction of the backend's ErrorResponse.message —
        falls back to a generic message if the body isn't JSON-shaped the
        way we expect (e.g. a proxy-generated error page)."""
        try:
            return str(response.json().get("message", "Request failed"))
        except ValueError:
            return "Request failed"

    async def complete_discord_setup(
        self, *, code: str, discord_guild_id: str, discord_guild_name: str, discord_user_id: str
    ) -> DiscordSetupResult:
        """POST /api/v1/discord/setup/complete — exchanges the one-time
        setup code for a GuildLink. Every failure mode (invalid/expired/
        already-used code, guild already linked to another org, transport
        error) collapses to `ok=False` with a human-readable message; the
        command handler just needs to know whether to show success or
        failure, not which specific exception type fired."""
        try:
            response = await self._http.post(
                "/api/v1/discord/setup/complete",
                json={
                    "code": code, "discord_guild_id": discord_guild_id, "discord_guild_name": discord_guild_name,
                    "discord_user_id": discord_user_id,
                },
                headers=self._bot_headers,
            )
        except httpx.HTTPError:
            return DiscordSetupResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return DiscordSetupResult(ok=False, error_message=self._error_message(response))
        return DiscordSetupResult(ok=True)

    async def get_guild_status(self, *, discord_guild_id: str) -> GuildStatusResult:
        """GET /api/v1/discord/guilds/{id}/status."""
        try:
            response = await self._http.get(
                f"/api/v1/discord/guilds/{discord_guild_id}/status", headers=self._bot_headers
            )
        except httpx.HTTPError:
            return GuildStatusResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return GuildStatusResult(ok=False, error_message=self._error_message(response))
        data = response.json()["data"]
        return GuildStatusResult(
            ok=True, linked=data["linked"], org_name=data.get("org_name"),
            discord_guild_name=data.get("discord_guild_name"),
        )

    async def unlink_guild(self, *, discord_guild_id: str, discord_user_id: str) -> UnlinkResult:
        """POST /api/v1/discord/guilds/{id}/unlink."""
        try:
            response = await self._http.post(
                f"/api/v1/discord/guilds/{discord_guild_id}/unlink",
                json={"discord_user_id": discord_user_id},
                headers=self._bot_headers,
            )
        except httpx.HTTPError:
            return UnlinkResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return UnlinkResult(ok=False, error_message=self._error_message(response))
        return UnlinkResult(ok=True)

    def _ticket_from_data(self, data: dict) -> TicketData:
        return TicketData(
            id=str(data["id"]), ticket_number=data["ticket_number"], discord_channel_id=data["discord_channel_id"],
            title=data["title"], status=data["status"], claimed_by_discord_user_id=data.get("claimed_by_discord_user_id"),
        )

    async def list_ticket_categories(self, *, discord_guild_id: str) -> TicketCategoriesResult:
        """GET /api/v1/discord/guilds/{id}/ticket-categories — populates the
        ticket panel's buttons/select menu."""
        try:
            response = await self._http.get(
                f"/api/v1/discord/guilds/{discord_guild_id}/ticket-categories", headers=self._bot_headers
            )
        except httpx.HTTPError:
            return TicketCategoriesResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return TicketCategoriesResult(ok=False, error_message=self._error_message(response))
        data = response.json()["data"]
        categories = [
            TicketCategoryData(
                id=str(c["id"]), name=c["name"], discord_category_channel_id=c["discord_category_channel_id"],
                staff_discord_role_ids=c.get("staff_discord_role_ids", []),
            )
            for c in data
        ]
        return TicketCategoriesResult(ok=True, categories=categories)

    async def create_ticket_category(
        self, *, discord_guild_id: str, name: str, discord_category_channel_id: str,
        staff_discord_role_ids: list[str],
    ) -> TicketCategoryResult:
        """POST /api/v1/discord/guilds/{id}/ticket-categories."""
        try:
            response = await self._http.post(
                f"/api/v1/discord/guilds/{discord_guild_id}/ticket-categories",
                json={
                    "discord_guild_id": discord_guild_id, "name": name,
                    "discord_category_channel_id": discord_category_channel_id,
                    "staff_discord_role_ids": staff_discord_role_ids,
                },
                headers=self._bot_headers,
            )
        except httpx.HTTPError:
            return TicketCategoryResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return TicketCategoryResult(ok=False, error_message=self._error_message(response))
        data = response.json()["data"]
        return TicketCategoryResult(
            ok=True,
            category=TicketCategoryData(
                id=str(data["id"]), name=data["name"], discord_category_channel_id=data["discord_category_channel_id"],
                staff_discord_role_ids=data.get("staff_discord_role_ids", []),
            ),
        )

    async def create_ticket(
        self, *, discord_guild_id: str, discord_channel_id: str, title: str, opener_discord_user_id: str
    ) -> TicketResult:
        """POST /api/v1/discord/tickets — called after the ticket channel
        has already been created in Discord (the backend never talks to
        Discord's API directly; the bot does, then reports the result)."""
        try:
            response = await self._http.post(
                "/api/v1/discord/tickets",
                json={
                    "discord_guild_id": discord_guild_id, "discord_channel_id": discord_channel_id, "title": title,
                    "opener_discord_user_id": opener_discord_user_id,
                },
                headers=self._bot_headers,
            )
        except httpx.HTTPError:
            return TicketResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return TicketResult(ok=False, error_message=self._error_message(response))
        return TicketResult(ok=True, ticket=self._ticket_from_data(response.json()["data"]))

    async def get_ticket_by_channel(self, *, discord_channel_id: str) -> TicketResult:
        """GET /api/v1/discord/tickets/by-channel/{id} — resolves which
        ticket a control-view interaction belongs to from the channel it
        fired in, so a single global view instance can serve every ticket
        channel without embedding a ticket id in each custom_id."""
        try:
            response = await self._http.get(
                f"/api/v1/discord/tickets/by-channel/{discord_channel_id}", headers=self._bot_headers
            )
        except httpx.HTTPError:
            return TicketResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return TicketResult(ok=False, error_message=self._error_message(response))
        return TicketResult(ok=True, ticket=self._ticket_from_data(response.json()["data"]))

    async def claim_ticket(self, *, ticket_id: str, claimant_discord_user_id: str) -> TicketResult:
        try:
            response = await self._http.post(
                f"/api/v1/discord/tickets/{ticket_id}/claim",
                json={"claimant_discord_user_id": claimant_discord_user_id},
                headers=self._bot_headers,
            )
        except httpx.HTTPError:
            return TicketResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return TicketResult(ok=False, error_message=self._error_message(response))
        return TicketResult(ok=True, ticket=self._ticket_from_data(response.json()["data"]))

    async def unclaim_ticket(self, *, ticket_id: str) -> TicketResult:
        try:
            response = await self._http.post(f"/api/v1/discord/tickets/{ticket_id}/unclaim", headers=self._bot_headers)
        except httpx.HTTPError:
            return TicketResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return TicketResult(ok=False, error_message=self._error_message(response))
        return TicketResult(ok=True, ticket=self._ticket_from_data(response.json()["data"]))

    async def transfer_ticket(self, *, ticket_id: str, new_claimant_discord_user_id: str) -> TicketResult:
        try:
            response = await self._http.post(
                f"/api/v1/discord/tickets/{ticket_id}/transfer",
                json={"new_claimant_discord_user_id": new_claimant_discord_user_id},
                headers=self._bot_headers,
            )
        except httpx.HTTPError:
            return TicketResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return TicketResult(ok=False, error_message=self._error_message(response))
        return TicketResult(ok=True, ticket=self._ticket_from_data(response.json()["data"]))

    async def close_ticket(self, *, ticket_id: str, closed_by_discord_user_id: str) -> TicketResult:
        try:
            response = await self._http.post(
                f"/api/v1/discord/tickets/{ticket_id}/close",
                json={"closed_by_discord_user_id": closed_by_discord_user_id},
                headers=self._bot_headers,
            )
        except httpx.HTTPError:
            return TicketResult(ok=False, error_message="Could not reach the GuildDesk API")
        if response.status_code >= 400:
            return TicketResult(ok=False, error_message=self._error_message(response))
        return TicketResult(ok=True, ticket=self._ticket_from_data(response.json()["data"]))

    async def aclose(self) -> None:
        await self._http.aclose()
