"""Tests fuer die Tool-Registry (class-based, DI, Lazy Loading)."""
from tools.base import BaseTool, ToolResult
from tools.registry import ToolRegistry


class StubTool(BaseTool):
    name = "stub"
    description = "Stub-Tool fuer Registry-Tests."
    parameters = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        return ToolResult.success(data={"ok": True})


def test_register_and_get():
    reg = ToolRegistry()
    reg.register(StubTool())
    assert "stub" in reg.names()
    assert reg.get("stub") is not None


def test_register_factory():
    calls = []

    def factory():
        calls.append(1)
        return StubTool()

    reg = ToolRegistry()
    reg.register(factory=factory)
    # Beim Registrieren wird die Factory einmal aufgerufen (fuer den Namen).
    assert len(calls) == 1
    tool = reg.get("stub")
    assert tool is not None
    # get() erzeugt eine frische Instanz (zustandsfrei).
    assert len(calls) == 2


def test_duplicate_rejected():
    reg = ToolRegistry()
    reg.register(StubTool())
    # Zweite Registrierung mit gleichem Namen wirft oder ersetzt kontrolliert
    try:
        reg.register(StubTool())
        names = reg.names().count("stub")
        assert names in (1,)
    except ValueError:
        pass


def test_definitions_openai_compatible():
    reg = ToolRegistry()
    reg.register(StubTool())
    defs = reg.definitions()
    assert defs[0]["type"] == "function"
    assert "function" in defs[0]
    assert defs[0]["function"]["name"] == "stub"