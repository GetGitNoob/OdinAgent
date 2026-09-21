"""ODIN Agent - LLM Client.

Wrappt die OpenAI-kompatible API (lokal, z. B. llama.cpp/Bonsai).
Konfiguration kommt aus Config (.env) - NIE hart im Code.
Stellt die LLM-Calls bereit und isoliert die LLM-Kommunikation.
"""
from __future__ import annotations

import time
from typing import Any

from openai import OpenAI

from config import Config


class LLMError(Exception):
    """Wird geworfen, wenn der LLM nicht erreichbar / Fehler liefert."""


class LLMClient:
    def __init__(self, config: Config) -> None:
        self.config = config

        if not config.llm_model:
            raise ValueError("LLM_MODEL ist nicht konfiguriert (.env)")

        self.client = OpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key or "local-",
            timeout=60.0,
            max_retries=1,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.config.llm_model)

    def check_available(self) -> bool:
        """Leichter Health-Check: Server erreichbar?  (model list)"""
        try:
            self.client.models.list(timeout=5)
            return True
        except Exception:
            return False

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 512,
    ) -> dict:
        """Einfacher Nicht-Streaming-Call.

        Rueckgabe: {"content": str|None, "tool_calls": [...]|None, "usage": ...}
        Wirft LLMError bei Fehler/Zeitueberschreitung.
        """
        start = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "model": self.config.llm_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": False,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"LLM nicht erreichbar: {e}") from e

        duration = time.perf_counter() - start
        choice = response.choices[0]
        message = choice.message

        tool_calls_raw = getattr(message, "tool_calls", None)
        tool_calls = None
        if tool_calls_raw:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls_raw
            ]

        usage = None
        try:
            usage = self._usage_to_dict(response.usage)
        except Exception:
            usage = None

        return {
            "content": getattr(message, "content", None) or None,
            "tool_calls": tool_calls,
            "usage": usage,
            "duration": duration,
        }

    @staticmethod
    def _usage_to_dict(usage) -> dict | None:
        if usage is None:
            return None
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }