"""
Plugin Loader: discovers plugin manifests, validates version compatibility
and extension-point support, then loads the plugin's entry point behind the
configured PluginSandbox.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from app.platform_core.logging.logger import get_logger
from app.platform_core.plugins.contracts import Plugin, PluginManifest
from app.platform_core.plugins.extension_points import assert_extension_point_designed
from app.platform_core.plugins.version_compat import SemVer, check_compatible

_logger = get_logger("plugins.loader")


class PluginLoadError(Exception):
    pass


class PluginLoader:
    def __init__(self, *, host_sdk_version: str, plugins_dir: Path) -> None:
        self._host_sdk_version = SemVer.parse(host_sdk_version)
        self._plugins_dir = plugins_dir
        self._loaded: dict[str, Plugin] = {}

    def discover_manifests(self) -> list[PluginManifest]:
        manifests: list[PluginManifest] = []
        for manifest_path in self._plugins_dir.glob("*/plugin.json"):
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifests.append(PluginManifest.model_validate(raw))
        return manifests

    async def load(self, manifest: PluginManifest) -> Plugin:
        check_compatible(
            plugin_id=manifest.plugin_id,
            host_sdk_version=self._host_sdk_version,
            min_sdk_version=SemVer.parse(manifest.min_sdk_version),
            max_sdk_version=SemVer.parse(manifest.max_sdk_version) if manifest.max_sdk_version else None,
        )
        for category in manifest.extension_points:
            assert_extension_point_designed(category)

        module_path, _, attr_name = manifest.entry_point.partition(":")
        module = importlib.import_module(module_path)
        plugin_cls = getattr(module, attr_name)
        plugin: Plugin = plugin_cls()

        await plugin.on_load()
        self._loaded[manifest.plugin_id] = plugin
        await _logger.ainfo("plugin_loaded", plugin_id=manifest.plugin_id, version=manifest.version)
        return plugin

    async def unload(self, plugin_id: str) -> None:
        plugin = self._loaded.pop(plugin_id, None)
        if plugin is not None:
            await plugin.on_unload()
            await _logger.ainfo("plugin_unloaded", plugin_id=plugin_id)
