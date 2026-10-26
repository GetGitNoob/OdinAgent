from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._factories: dict[str, Callable[[], BaseTool]] = {}

    def register(
        self,
        tool: BaseTool | None = None,
        *,
        tool_class: type[BaseTool] | None = None,
        factory: Callable[[], BaseTool] | None = None,
    ) -> None:
        if tool is not None:
            self._tools[tool.name] = tool
            return

        if tool_class is not None:
            instance = tool_class()
            self._tools[instance.name] = instance
            return

        if factory is not None:
            instance = factory()
            self._factories[instance.name] = factory
            self._tools[instance.name] = instance
            return

        raise ValueError("register() benötigt tool, tool_class oder factory.")

    def get(self, name: str) -> BaseTool | None:
        if name in self._tools:
            return self._tools[name]

        if name in self._factories:
            tool = self._factories[name]()
            self._tools[name] = tool
            return tool

        return None

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.definition for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self.get(name)

        if tool is None:
            from tools.base import ToolResult
            return ToolResult.fail(f"Unbekanntes Tool: {name}")

        return tool.execute(arguments)


def build_default_registry(tools: list[BaseTool]) -> ToolRegistry:
    registry = ToolRegistry()

    for tool in tools:
        registry.register(tool)

    return registry


_default_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _default_registry

    if _default_registry is None:
        from config import Config

        from tools.hindsight import HindsightRecallTool, HindsightRetainTool
        from tools.calculator import CalculatorTool
        from tools.filesystem import FilesystemTool
        from tools.image_analysis import ImageAnalysisTool
        from tools.system import SystemTool
        from tools.terminal import TerminalTool
        from tools.web_search import WebSearchTool

        cfg = Config.load()

        _default_registry = build_default_registry(
            [
                HindsightRecallTool(),
                HindsightRetainTool(),
                CalculatorTool(),
                TerminalTool(
                    timeout=cfg.terminal_timeout,
                    max_output=cfg.terminal_max_output,
                ),
                FilesystemTool(
                    allowed_roots=cfg.filesystem_allowed_roots,
                ),
                SystemTool(),
                WebSearchTool(),
                ImageAnalysisTool(
                    api_base_url=cfg.llm_base_url,
                    model=cfg.llm_model or "qwen3.8-27b",
                    api_key=cfg.llm_api_key,
                ),
            ]
        )

    return _default_registry
