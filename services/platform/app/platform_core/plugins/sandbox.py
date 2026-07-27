"""
Sandbox Interfaces: the isolation boundary Protocol untrusted plugin code
runs behind. The concrete sandbox technology (subprocess + resource limits,
gVisor, WASM per the Technical Radar's "Trial" entry for WASM Plugins) is
not decided here — this Protocol is the seam PluginLoader depends on, kept
deliberately minimal so any of those options can implement it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    success: bool
    output: Any
    error: str | None
    duration_ms: float


class SandboxTimeoutError(Exception):
    pass


class PluginSandbox(Protocol):
    async def execute(
        self, *, entry_point: str, function_name: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> SandboxExecutionResult: ...
