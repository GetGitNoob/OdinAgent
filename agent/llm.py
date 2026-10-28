"""ODIN Agent - LLM Client.

Wrappt die OpenAI-kompatible API (lokal, z. B. llama.cpp/Bonsai).
Konfiguration kommt aus Config (.env) - NIE hart im Code.
Stellt die LLM-Calls bereit und isoliert die LLM-Kommunikation.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from openai import OpenAI

from config import Config


class LLMError(Exception):
    """Wird geworfen, wenn der LLM nicht erreichbar / Fehler liefert."""


class LLMClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        # Kein Fehler beim Konstruieren: auch ohne LLM_MODEL muss der
        # Webserver hochkommen und /api/health "degraded" melden.
        # Der OpenAI-Client wird erst bei Bedarf angelegt (lazy).
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.config.llm_model)

    def _get_client(self) -> "OpenAI | None":
        """Erzeugt den OpenAI-Client lazy; None, wenn kein Modell gesetzt."""
        if not self.config.llm_model:
            return None
        if self._client is None:
            # Getrennte Timeouts pro httpx-Phase (openai 3.16.2 / httpx 0.28.1):
            # - connect: 10 s  (Server muss schnell antworten)
            # - read:    600 s (lange Generierungen duerfen >120 s dauern)
            # - write:   60 s  (Request-Body ist klein)
            # - pool:    30 s  (Warten auf freie Verbindung)
            self._client = OpenAI(
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key or "local-",
                timeout=httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=30.0),
                max_retries=1,
            )
        return self._client

    def check_available(self) -> bool:
        """Leichter Health-Check: Server erreichbar?  (model list)"""
        client = self._get_client()
        if client is None:
            return False
        try:
            client.models.list(timeout=120.0)
            return True
        except Exception:
            return False

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Einfacher Nicht-Streaming-Call.

        Rueckgabe: {"content": str|None, "tool_calls": [...]|None, "usage": ...}
        Wirft LLMError bei Fehler/Zeitueberschreitung.
        """
        start = time.perf_counter()
        client = self._get_client()
        if client is None:
            raise LLMError("LLM ist nicht konfiguriert (.env fehlt LLM_MODEL)")
        try:
            kwargs: dict[str, Any] = {
                "model": self.config.llm_model,
                "messages": messages,
                "max_tokens": (
                    max_tokens
                    if max_tokens is not None
                    else self.config.llm_max_tokens
                ),
                "temperature": 0.2,
                "reasoning_effort": "medium",
                "stream": False,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)
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
