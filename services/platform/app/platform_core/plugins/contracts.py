"""Plugin Contracts: the manifest shape every plugin ships (Plugin-Manifest.md,
Plugin-Architecture.md), and the base Plugin interface it implements."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class PluginManifest(BaseModel):
    plugin_id: str
    name: str
    version: str  # semver
    min_sdk_version: str  # semver
    max_sdk_version: str | None = None  # semver, None = no upper bound
    extension_points: list[str]  # e.g. ["backend", "notification", "integration"]
    entry_point: str  # importable module:attribute path


class Plugin(Protocol):
    manifest: PluginManifest

    async def on_load(self) -> None: ...

    async def on_unload(self) -> None: ...
