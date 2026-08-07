"""Plugin base and tool router."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


ToolHandler = Callable[..., Awaitable[Any] | Any]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


class Plugin(ABC):
    name: str

    @abstractmethod
    def tools(self) -> list[ToolSpec]:
        raise NotImplementedError


class ToolRouter:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register_plugin(self, plugin: Plugin) -> None:
        for tool in plugin.tools():
            self._tools[tool.name] = tool

    def openai_tools(self) -> list[dict[str, Any]]:
        result = []
        for tool in self._tools.values():
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return result

    async def execute(self, name: str, arguments: str | dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        else:
            args = arguments
        handler = self._tools[name].handler
        result = handler(**args)
        if hasattr(result, "__await__"):
            return await result
        return result

    def has_tools(self) -> bool:
        return bool(self._tools)
