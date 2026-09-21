"""ODIN Agent - Agent Loop (Core).

Unabhaengig vom Kommunikationskanal. Der Kanal liefert:
  session_id, message
und bekommt zurueck:  response (Generator fuer Streaming).

Verantwortlichkeiten:
  - LLM-Calls (via LLMClient)
  - Tool-Calling-Loop (mehrere Calls/Relais)
  - Konversations-Historie laden/speichern
  - Metriken (LLM- und Tool-Duration) sammeln

OHNE Kanal-spezifische Logik. Browser und WhatsApp sind Adapter.
"""
from __future__ import annotations

import json
from typing import Callable, Generator

from agent.context import AgentContext
from agent.llm import LLMClient, LLMError
from conversation import ConversationStore
from tools.base import ToolResult
from tools.registry import ToolRegistry


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        conversations: ConversationStore,
        context: AgentContext,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.conversations = conversations
        self.context = context

    # ---------------------------------------------------------
    # Haupt-Einstiegspunkt fuer einen Kanal. Liefert finale Antwort + Tool-Log.
    # ---------------------------------------------------------

    def handle_message(
        self,
        session_id: str,
        message: str,
    ) -> dict:
        """Verarbeitet eine Nachricht und liefert eine finale Antwort.

        Stellt das Tool-Calling-Relais sicher. Gibt einen dict mit:
          { "content": str, "tools": [...], "error": bool }
        zurueck. Web-UI streamt separat; hier kommt die offizielle Antwort.
        """
        conv = self.conversations.get_or_create(session_id)
        history = conv.get("messages", [])

        # User-Nachricht anhaengen + persistieren
        user_msg = {"role": "user", "content": message}
        history.append(user_msg)
        self.conversations.append_message(session_id, user_msg)

        messages = self.context.build_messages(history)
        meta = {"tools": [], "error": False}

        # Beginne relais Tool-Loop (max. MAX_TOOL_ITERATIONS Runden)
        max_rounds = 6
        for _ in range(max_rounds):
            try:
                result = self.llm.chat(
                    messages,
                    tools=self.tools.definitions(),  # lazy -> nur nötige
                )
            except LLMError as e:
                meta["error"] = True
                final = self._llm_fallback(str(e))
                self.conversations.append_message(
                    session_id, {"role": "assistant", "content": final}
                )
                return {"content": final, "tools": meta["tools"], "error": True}

            asst_content = result.get("content")
            tool_calls = result.get("tool_calls")

            # Kein Tool-Call -> finale Antwort
            if not tool_calls:
                self.conversations.append_message(
                    session_id,
                    {"role": "assistant", "content": asst_content or ""},
                )
                return {
                    "content": asst_content or "",
                    "tools": meta["tools"],
                    "error": False,
                }

            # --- Tool-Call(s) ausfuehren --------------------
            messages.append(
                {
                    "role": "assistant",
                    "content": asst_content or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"]["arguments"],
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_result = self._run_tool(name, args)
                meta["tools"].append(
                    {
                        "name": name,
                        "arguments": args,
                        "result": tool_result.to_dict(),
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(
                            tool_result.to_dict(), ensure_ascii=False
                        ),
                    }
                )

        # Max. Runden erreicht -> Abbruch
        final = "Maximale Anzahl an Tool-Aufrufen erreicht. Bitte präzisiere."
        self.conversations.append_message(
            session_id, {"role": "assistant", "content": final}
        )
        return {"content": final, "tools": meta["tools"], "error": False}

    # ---------------------------------------------------------

    def _run_tool(self, name: str, args: dict) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult.fail(error=f"Unbekanntes Tool: {name}")
        try:
            return tool.run(**args)
        except TypeError as e:
            return ToolResult.fail(error=f"Parameterfehler bei {name}: {e}")
        except Exception as e:  # noqa: BLE001
            return ToolResult.fail(error=f"{name} Fehler: {e}")

    def _llm_fallback(self, err: str) -> str:
        return (
            "Entschuldigung, die KI-Verbindung ist gerade nicht erreichbar. "
            f"(Details: {err})"
        )