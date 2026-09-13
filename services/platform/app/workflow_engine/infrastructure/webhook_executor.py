"""
HTTP-based implementation of WebhookExecutorPort — the EXECUTE_WEBHOOK
workflow action. No other bounded context has needed outbound HTTP before,
so this is a new, self-contained capability introduced within Workflow
Engine's own infrastructure (not a Platform Core change) — the same kind
of first-use-introduces-the-infra precedent Tasks set for JobScheduler and
Boards set for the daily burndown job.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any

import httpx

from app.platform_core.shared_kernel.constants import TIMEOUT_EXTERNAL_SECONDS
from app.workflow_engine.domain.exceptions import WebhookExecutionFailedError

IpAddress = IPv4Address | IPv6Address
AddressResolver = Callable[[str, int], Awaitable[set[IpAddress]]]


async def _resolve_addresses(hostname: str, port: int) -> set[IpAddress]:
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(
        hostname,
        port,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return {
        ip_address(record[4][0].split("%", maxsplit=1)[0])
        for record in records
    }


class HttpxWebhookExecutor:
    def __init__(
        self,
        *,
        timeout_seconds: float = TIMEOUT_EXTERNAL_SECONDS,
        address_resolver: AddressResolver = _resolve_addresses,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._address_resolver = address_resolver
        self._transport = transport

    async def execute(self, *, url: str, payload: dict[str, Any]) -> None:
        await self._assert_public_https_destination(url)
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WebhookExecutionFailedError("Webhook request failed") from exc

    async def _assert_public_https_destination(self, url: str) -> None:
        try:
            parsed = httpx.URL(url)
            hostname = parsed.host
            port = parsed.port or 443
        except (TypeError, httpx.InvalidURL) as exc:
            raise WebhookExecutionFailedError("Webhook URL is invalid") from exc

        if parsed.scheme.lower() != "https" or not hostname:
            raise WebhookExecutionFailedError(
                "Webhook URL must be an absolute HTTPS URL"
            )
        if parsed.userinfo:
            raise WebhookExecutionFailedError(
                "Webhook URL must not contain embedded credentials"
            )

        normalized_hostname = hostname.rstrip(".").lower()
        if normalized_hostname == "localhost" or normalized_hostname.endswith(
            (".localhost", ".local", ".internal")
        ):
            raise WebhookExecutionFailedError(
                "Webhook URL must resolve only to public network addresses"
            )

        try:
            addresses = await self._address_resolver(hostname, port)
        except (OSError, ValueError) as exc:
            raise WebhookExecutionFailedError(
                "Webhook destination could not be resolved"
            ) from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise WebhookExecutionFailedError(
                "Webhook URL must resolve only to public network addresses"
            )
