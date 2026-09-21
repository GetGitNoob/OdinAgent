"""Tests fuer den Agent-Loop (Tool-Calling-Zyklus, Kanal-unabhaengig)."""
import pytest

from agent.context import AgentContext
from agent.llm import LLMClient
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