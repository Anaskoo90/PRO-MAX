from __future__ import annotations

import json
from ipaddress import ip_address

import httpx
import pytest
from app.workflow_engine.domain.exceptions import WebhookExecutionFailedError
from app.workflow_engine.infrastructure.webhook_executor import HttpxWebhookExecutor

pytestmark = pytest.mark.asyncio


async def _public_resolver(hostname: str, port: int):
    assert hostname == "hooks.example.com"
    assert port == 443
    return {ip_address("93.184.216.34")}


async def _private_resolver(hostname: str, port: int):
    return {ip_address("10.0.0.8")}


async def test_public_https_webhook_is_posted_without_reading_a_response_body() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    executor = HttpxWebhookExecutor(
        address_resolver=_public_resolver,
        transport=httpx.MockTransport(handler),
    )

    await executor.execute(
        url="https://hooks.example.com/events",
        payload={"event": "task.completed"},
    )

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert json.loads(requests[0].content) == {"event": "task.completed"}


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/events",
        "https://localhost/events",
        "https://service.internal/events",
        "https://user:password@hooks.example.com/events",
        "not-a-url",
    ],
)
async def test_webhook_rejects_insecure_or_internal_urls_before_sending(url: str) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    executor = HttpxWebhookExecutor(
        address_resolver=_public_resolver,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WebhookExecutionFailedError):
        await executor.execute(url=url, payload={})

    assert requests == []


async def test_webhook_rejects_a_hostname_resolving_to_a_private_address() -> None:
    executor = HttpxWebhookExecutor(
        address_resolver=_private_resolver,
        transport=httpx.MockTransport(lambda request: httpx.Response(204)),
    )

    with pytest.raises(WebhookExecutionFailedError, match="public network"):
        await executor.execute(url="https://hooks.example.com/events", payload={})


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/admin",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/admin",
    ],
)
async def test_webhook_rejects_private_and_metadata_ip_literals(url: str) -> None:
    executor = HttpxWebhookExecutor(
        transport=httpx.MockTransport(lambda request: httpx.Response(204))
    )

    with pytest.raises(WebhookExecutionFailedError, match="public network"):
        await executor.execute(url=url, payload={})


async def test_webhook_rejects_mixed_public_and_private_dns_answers() -> None:
    async def mixed_resolver(hostname: str, port: int):
        return {ip_address("93.184.216.34"), ip_address("192.168.1.5")}

    executor = HttpxWebhookExecutor(
        address_resolver=mixed_resolver,
        transport=httpx.MockTransport(lambda request: httpx.Response(204)),
    )

    with pytest.raises(WebhookExecutionFailedError, match="public network"):
        await executor.execute(url="https://hooks.example.com/events", payload={})


async def test_webhook_does_not_follow_redirects() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"})

    executor = HttpxWebhookExecutor(
        address_resolver=_public_resolver,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WebhookExecutionFailedError, match="request failed"):
        await executor.execute(url="https://hooks.example.com/events", payload={})

    assert len(requests) == 1


async def test_webhook_maps_dns_failures_without_exposing_the_url() -> None:
    async def failing_resolver(hostname: str, port: int):
        raise OSError("dns unavailable")

    executor = HttpxWebhookExecutor(address_resolver=failing_resolver)

    with pytest.raises(WebhookExecutionFailedError, match="could not be resolved") as exc_info:
        await executor.execute(
            url="https://hooks.example.com/events?secret=do-not-expose",
            payload={},
        )

    assert "do-not-expose" not in str(exc_info.value)
