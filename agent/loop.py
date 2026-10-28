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
import logging
import time
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
        self.last_prompt_tokens = None

    # ---------------------------------------------------------
    # Event-Helfer: feuert optionale on_event-Callbacks, ohne dass
    # ein Fehler im Callback den Agent-Loop abbrechen kann.
    # ---------------------------------------------------------

    @staticmethod
    def _emit(on_event, event_type: str, **payload) -> None:
        if on_event is None:
            return
        try:
            on_event({"type": event_type, **payload})
        except Exception:  # noqa: BLE001
            logging.getLogger("odin-agent").debug(
                "on_event-Callback fehlgeschlagen (ignoriert): type=%s",
                event_type,
                exc_info=True,
            )

    # ---------------------------------------------------------
    # Haupt-Einstiegspunkt fuer einen Kanal. Liefert finale Antwort + Tool-Log.
    # ---------------------------------------------------------

    def handle_message(
        self,
        session_id: str,
        message: str,
        on_event: Callable[[dict], None] | None = None,
    ) -> dict:
        """Verarbeitet eine Nachricht und liefert eine finale Antwort.

        Stellt das Tool-Calling-Relais sicher. Gibt einen dict mit:
          { "content": str, "tools": [...], "error": bool }
        zurueck. Web-UI streamt separat; hier kommt die offizielle Antwort.

        on_event (optional): Wird bei realen Ereignissen aufgerufen
        (LLM-Runde, Tool-Start/-Fertig). Dient z. B. der Web-UI fuer
        Live-Zwischenstaende. Callback-Fehler werden geschluckt.
        """
        conv = self.conversations.get_or_create(session_id)
        history = conv.get("messages", [])

        # User-Nachricht anhaengen + persistieren
        user_msg = {"role": "user", "content": message}
        history.append(user_msg)
        self.conversations.append_message(session_id, user_msg)

        messages = self.context.build_messages(history)
        meta = {"tools": [], "error": False}
        last_tool_signature = None
        repeated_tool_count = 0
        repeat_limit = 10
        last_tool_error = None  # Letzter konkreter Tool-Fehler fuer Diagnose

        # Beginne relais Tool-Loop (max. MAX_TOOL_ITERATIONS Runden)
        max_rounds = 100
        for round_no in range(max_rounds):
            self._emit(on_event, "llm_start", round=round_no + 1)
            try:
                result = self.llm.chat(
                    messages,
                    tools=self.tools.definitions(),  # lazy -> nur nötige
                )
                usage = result.get('usage') or {}
                prompt_tokens = usage.get('prompt_tokens')
                if isinstance(prompt_tokens, (int, float)) and prompt_tokens >= 0:
                    self.last_prompt_tokens = int(prompt_tokens)
            except LLMError as e:
                meta["error"] = True
                final = self._llm_fallback(str(e))
                self.conversations.append_message(
                    session_id, {"role": "assistant", "content": final}
                )
                return {"content": final, "tools": meta["tools"], "error": False}

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
                signature = json.dumps(
                    {"name": name, "arguments": args},
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

                if signature == last_tool_signature:
                    repeated_tool_count += 1
                else:
                    last_tool_signature = signature
                    repeated_tool_count = 1

                if repeated_tool_count >= repeat_limit:
                    # Konkrete Diagnose: letzter Fehler + Befehl + Anzahl
                    cmd_hint = ""
                    if isinstance(args, dict):
                        cmd_val = args.get("command") or args.get("query") or args.get("path") or ""
                        if cmd_val:
                            cmd_hint = f" (Befehl/Argument: {str(cmd_val)[:200]!r})"

                    err_hint = ""
                    if last_tool_error:
                        err_hint = f"\nLetzte Fehlermeldung: {last_tool_error[:500]}"

                    final = (
                        f"Sicherheitsabbruch: Tool {name!r} wurde "
                        f"{repeated_tool_count} Mal hintereinander mit "
                        f"identischen Argumenten angefordert.{cmd_hint}{err_hint}\n"
                        f"Der gleiche Aufruf liefert ohne neue Erkenntnisse "
                        f"dasselbe Ergebnis. Bitte die Argumente aendern oder "
                        f"eine andere Diagnose verwenden."
                    )

                    logging.getLogger("odin-agent").warning(
                        "Sicherheitsabbruch: wiederholter Tool-Aufruf name=%s count=%d last_error=%s",
                        name,
                        repeated_tool_count,
                        (last_tool_error or "")[:200],
                    )

                    self.conversations.append_message(
                        session_id, {"role": "assistant", "content": final}
                    )

                    return {
                        "content": final,
                        "tools": meta["tools"],
                        "error": True,
                    }

                self._emit(on_event, "tool_start", name=name, arguments=args)
                t0 = time.monotonic()
                tool_result = self._run_tool(name, args)
                duration = round(time.monotonic() - t0, 2)
                # Letzten konkreten Fehler merken fuer moeglichen Sicherheitsabbruch
                if not tool_result.success and tool_result.error:
                    last_tool_error = tool_result.error
                else:
                    last_tool_error = None
                meta["tools"].append(
                    {
                        "name": name,
                        "arguments": args,
                        "result": tool_result.to_dict(),
                    }
                )
                self._emit(
                    on_event,
                    "tool_done",
                    name=name,
                    success=bool(tool_result.success),
                    duration=duration,
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

        # Limit erreicht: bisherigen Fortschritt ohne weitere Tools zusammenfassen

        logger = logging.getLogger("odin-agent")

        logger.warning(
            "Tool-Rundenlimit erreicht: rounds=%d, ausgeführte_tools=%d",
            max_rounds, len(meta["tools"]),
        )

        progress = json.dumps(meta["tools"], ensure_ascii=False, indent=2)

        summary_messages = messages + [{
            "role": "user",
            "content": (
                f"Du hast das Limit von {max_rounds} Agent-Runden erreicht. "
                "Führe keine weiteren Tools aus. Erstelle anhand der bisherigen "
                "Unterhaltung und der protokollierten Tool-Ergebnisse einen "
                "ehrlichen Zwischenbericht auf Deutsch. Gliedere ihn in "
                "'Bisher herausgefunden', 'Bereits erledigt', 'Noch offen' und "
                "'Nächster sinnvoller Schritt'. Trenne Fakten von Vermutungen "
                "und behaupte keine nicht ausgeführten Aktionen.\n\n"
                "Bisherige Tool-Ergebnisse:\n" + progress
            ),
        }]

        try:
            summary_result = self.llm.chat(summary_messages, tools=None)
            final = (summary_result.get("content") or "").strip()
            if not final:
                raise ValueError("Leere Fortschrittszusammenfassung")
        except Exception as e:
            logger.warning("Fortschrittszusammenfassung fehlgeschlagen: %s", e)
            names = [item.get("name", "unbekannt") for item in meta["tools"]]
            recent = ", ".join(names[-10:]) if names else "Keine Tools ausgeführt"
            final = (
                f"Ich habe mein Limit von {max_rounds} Runden erreicht. "
                f"Ausgeführt wurden {len(meta['tools'])} Tool-Aufrufe. "
                f"Zuletzt verwendete Tools: {recent}. "
                "Eine automatische Zusammenfassung war nicht möglich; "
                "der bisherige Fortschritt ist in den Tool-Logs enthalten."
            )

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
