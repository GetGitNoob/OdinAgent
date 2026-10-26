"""Tests fuer den Agent-Loop (Tool-Calling-Zyklus, Kanal-unabhaengig)."""
import pytest

from agent.context import AgentContext

from agent.loop import AgentLoop
from conversation import ConversationStore
from tools.calculator import CalculatorTool
from tools.registry import ToolRegistry


class FakeLLM:
    """Simuliert eine LLM-Session mit Tool-Calls + finaler Antwort."""

    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools})
        # Sequenz: erst Tool-Call, dann finale Antwort
        idx = len(self.calls)
        if idx == 1:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression": "6*7"}',
                        },
                    }
                ],
            }
        return {"content": "Die Antwort ist 42.", "tool_calls": None}


class RepeatingFakeLLM:
    """Simuliert eine LLM, die denselben Tool-Call immer wieder macht."""

    def __init__(self, repeat_count=15):
        self.calls = []
        self.repeat_count = repeat_count

    def chat(self, messages, tools=None, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools})
        # Immer denselben Tool-Call -> triggert Sicherheitsabbruch
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{len(self.calls)}",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": '{"command": "echo test"}',
                    },
                }
            ],
        }


@pytest.fixture
def loop(tmp_path):
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    class DummyConfig:
        system_prompt = "Test-Prompt"
        max_history_messages = 20

    llm = FakeLLM()
    conversations = ConversationStore(data_dir=str(tmp_path / "conv"))
    context = AgentContext(DummyConfig())

    return AgentLoop(
        llm=llm,
        tools=registry,
        conversations=conversations,
        context=context,
    ), llm


@pytest.fixture
def repeating_loop(tmp_path):
    """Loop mit Terminal-Tool und einer LLM die immer denselben Call macht."""
    from tools.terminal import TerminalTool

    registry = ToolRegistry()
    registry.register(TerminalTool(timeout=5))

    class DummyConfig:
        system_prompt = "Test-Prompt"
        max_history_messages = 20

    llm = RepeatingFakeLLM(repeat_count=15)
    conversations = ConversationStore(data_dir=str(tmp_path / "conv_repeat"))
    context = AgentContext(DummyConfig())

    return AgentLoop(
        llm=llm,
        tools=registry,
        conversations=conversations,
        context=context,
    ), llm


def test_handle_message_with_tool_call(loop):
    agent, llm = loop
    result = agent.handle_message("sess-1", "Berechne 6*7")

    assert result["content"] == "Die Antwort ist 42."
    assert result["tools"]  # mindestens ein Tool-Eintrag im Log
    assert any(t["name"] == "calculator" for t in result["tools"])

    # Konversation wurde persistiert (assistant-Antwort)
    hist = agent.conversations.load("sess-1")
    roles = [m["role"] for m in hist]
    assert "assistant" in roles
    assert "user" in roles


def test_handle_message_persists_user(loop):
    agent, _ = loop
    agent.handle_message("sess-2", "Hallo")
    hist = agent.conversations.load("sess-2")
    assert any(m["role"] == "user" and m["content"] == "Hallo" for m in hist)
    # assistant-Antwort wurde ebenfalls persistiert
    assert any(m["role"] == "assistant" for m in hist)


def test_safety_abort_includes_error_details(repeating_loop):
    """Sicherheitsabbruch muss konkrete Fehlerdetails enthalten, nicht nur 'True'."""
    agent, llm = repeating_loop
    result = agent.handle_message("sess-repeat", "Teste Wiederholung")

    # Muss abgebrochen haben (error=True)
    assert result["error"] is True
    content = result["content"]

    # Muss "Sicherheitsabbruch" enthalten
    assert "Sicherheitsabbruch" in content
    # Muss die Anzahl der Wiederholungen erwähnen
    assert "Mal hintereinander" in content or "identischen Argumenten" in content
    # Muss den Tool-Namen enthalten
    assert "terminal" in content
    # Darf NICHT nur "Fehler: True" sein
    assert "Fehler: True" not in content
    assert "Fehler: False" not in content


def test_safety_abort_mentions_command(repeating_loop):
    """Sicherheitsabbruch sollte den betroffenen Befehl/Argument erwähnen."""
    agent, llm = repeating_loop
    result = agent.handle_message("sess-cmd", "Teste Befehl")

    content = result["content"]
    # Der Befehl "echo test" sollte erwähnt werden
    assert "echo test" in content or "Befehl" in content
