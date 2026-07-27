"""
Extension Points.

Only three extension-point categories have ever been designed at the
architecture level (Plugin SDK & Extension Architecture): Backend,
Notification, Integration. UI, Dashboard, Workflow, and AI extension points
remain flagged as not designed — this module implements the three real
categories and intentionally does not stub the other five, so an attempt
to register one fails loudly (NotImplementedError) instead of silently
accepting a registration nothing will ever invoke.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from app.platform_core.notifications.dispatcher import NotificationRequest

# --- Backend extension point ------------------------------------------------

BackendHookHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class BackendExtensionPoint:
    """Plugins register a handler for a named backend hook (e.g.
    'ticket.before_create') and can inspect/augment the payload."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[BackendHookHandler]] = {}

    def register(self, hook_name: str, handler: BackendHookHandler) -> None:
        self._hooks.setdefault(hook_name, []).append(handler)

    async def invoke(self, hook_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        for handler in self._hooks.get(hook_name, []):
            payload = await handler(payload)
        return payload


# --- Notification extension point -------------------------------------------


class NotificationChannelProvider(Protocol):
    """A plugin-supplied delivery channel, dispatched through the same
    NotificationDispatcher core channels use (see platform_core.notifications)."""

    channel_key: str

    async def send(self, request: NotificationRequest) -> None: ...


class NotificationExtensionPoint:
    def __init__(self) -> None:
        self._providers: dict[str, NotificationChannelProvider] = {}

    def register(self, provider: NotificationChannelProvider) -> None:
        self._providers[provider.channel_key] = provider

    def get(self, channel_key: str) -> NotificationChannelProvider | None:
        return self._providers.get(channel_key)


# --- Integration extension point --------------------------------------------


class IntegrationProvider(Protocol):
    """A plugin-supplied external-system adapter, matching the Integration
    Layer's generalized provider-abstraction pattern (Amendment v2, ADR-034)."""

    provider_key: str

    async def call(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class IntegrationExtensionPoint:
    def __init__(self) -> None:
        self._providers: dict[str, IntegrationProvider] = {}

    def register(self, provider: IntegrationProvider) -> None:
        self._providers[provider.provider_key] = provider

    def get(self, provider_key: str) -> IntegrationProvider | None:
        return self._providers.get(provider_key)


# --- Not-yet-designed categories ---------------------------------------------

_NOT_DESIGNED_CATEGORIES = frozenset({"ui", "dashboard", "workflow", "ai"})


class ExtensionPointNotDesignedError(NotImplementedError):
    def __init__(self, category: str) -> None:
        super().__init__(
            f"Extension point category '{category}' has no design yet "
            "(Plugin SDK & Extension Architecture, standing gap)"
        )


def assert_extension_point_designed(category: str) -> None:
    if category in _NOT_DESIGNED_CATEGORIES:
        raise ExtensionPointNotDesignedError(category)
