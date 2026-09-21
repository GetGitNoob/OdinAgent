"""ODIN Agent - Tool Registry.

Class-based, Dependency-Injection-faehig. Tools werden per
ToolRegistry.register(...) hinzugefuegt. Lazy Tool Loading ist
vorgesehen: register() nimmt wahlweise ein Tool-Objekt ODER eine
Factory-Funktion (callable), die das Tool erst bei Bedarf erzeugt.
Der Agent Core kennt nur die Registry, keine konkreten Tools.
"""
from __future__ import annotations

from typing import Callable

from tools.base import BaseTool, ToolResult


class ToolRegistry:
    """Verwaltet alle verfuegbaren Tools.

    - register(tool_object)         -> direktes Objekt
    - register(tool_class=Cls)      -> pro Definition instanziiert
    - register(factory=<callable>)  -> Lazy: erst bei erster Ausfuehrung
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._factories: dict[str, Callable[[], BaseTool]] = {}

    # ---------------------------------------------------------
    # Registration
    # ---------------------------------------------------------

    def register(
        self,
        tool: BaseTool | None = None,
        *,
        tool_class: type[BaseTool] | None = None,
        factory: Callable[[], BaseTool] | None = None,
    ) -> None:
        if tool is not None:
            self._add_instance(tool)
        elif tool_class is not None:
            self._add_instance(tool_class())
        elif factory is not None:
            # Lazy Loading: Tool erst beim ersten Zugriff erzeugen.
            instance = factory()
            self._add(instance)
            self._factories[instance.name] = factory
        else:
            raise ValueError("register: tool, tool_class oder factory angeben")

    def _add_instance(self, tool: BaseTool) -> None:
        self._add(tool)

    def _add(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Doppeltes Tool registriert: {tool.name}")
        self._tools[tool.name] = tool

    # ---------------------------------------------------------
    # Abfragen
    # ---------------------------------------------------------

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise KeyError(f"Unbekanntes Tool: {name}")
        factory = self._factories.get(name)
        if factory is not None and name in self._tools:
            # Lazy: bei Bedarf neu instanziieren (frischer Zustand).
            self._tools[name] = factory()
        return self._tools[name]

    def definitions(self) -> list[dict]:
        return [tool.definition for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    # ---------------------------------------------------------
    # Ausfuehrung
    # ---------------------------------------------------------

    def execute(self, name: str, arguments: dict) -> ToolResult:
        if name not in self._tools:
            return ToolResult.fail(error=f"Unbekanntes Tool: {name}")
        return self.get(name).execute(arguments)


# ---------------------------------------------------------
# Singleton-Default-Instanz (Bequemlichkeit fuer Tests/Legacy)
# ---------------------------------------------------------

_default_registry: ToolRegistry | None = None


def build_default_registry(
    tools: list[BaseTool] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools or []:
        registry.register(tool)
    return registry


def get_registry() -> ToolRegistry:
    """Baut die globale Registry mit der geladenen Config auf."""
    global _default_registry
    if _default_registry is None:
        from config import Config
        from tools.calculator import CalculatorTool
        from tools.filesystem import FilesystemTool
        from tools.system import SystemTool
        from tools.terminal import TerminalTool

        cfg = Config.load()
        _default_registry = build_default_registry(
            [
                CalculatorTool(),
                TerminalTool(
                    timeout=cfg.terminal_timeout,
                    max_output=cfg.terminal_max_output,
                ),
                FilesystemTool(allowed_roots=cfg.filesystem_allowed_roots),
                SystemTool(),
            ]
        )
    return _default_registry


# ---------------------------------------------------------
# Backward-kompatibel zur alten funktionalen API
# ---------------------------------------------------------

def get_tool_definitions() -> list[dict]:
    return get_registry().definitions()


def execute_tool(name: str, arguments: dict) -> ToolResult:
    return get_registry().execute(name, arguments)