"""
Tool Calling Interface: the registry an LlmProvider's `tools` parameter is
built from, and the dispatcher that executes a model-requested tool call
against a real handler — the mechanism the AI Business Assistant uses to
act on the platform (e.g. "create a ticket") rather than only converse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters_schema: dict[str, Any]  # JSON Schema
    handler: ToolHandler


class UnknownToolError(Exception):
    def __init__(self, tool_name: str) -> None:
        super().__init__(f"No tool registered with name '{tool_name}'")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def as_llm_provider_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema,
            }
            for t in self._tools.values()
        ]

    async def invoke(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise UnknownToolError(tool_name)
        return await tool.handler(arguments)
