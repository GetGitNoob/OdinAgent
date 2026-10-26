"""Native Hindsight memory tools for ODIN."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from tools.base import BaseTool, ToolResult


class HindsightTool(BaseTool):
    base_url = os.getenv("HINDSIGHT_URL", "http://127.0.0.1:9177").rstrip("/")
    bank_id = os.getenv("HINDSIGHT_BANK_ID", "hermes")

    def request(self, endpoint: str, payload: dict[str, Any]) -> Any:
        url = (
            f"{self.base_url}/v1/default/banks/"
            f"{self.bank_id}/{endpoint}"
        )
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Hindsight HTTP {exc.code}: {detail}") from exc


class HindsightRecallTool(HindsightTool):
    name = "memory_recall"
    description = (
        "Sucht relevante Informationen und frühere Erfahrungen in "
        "Hindsight. Nutze das Tool, wenn frühere Gespräche, persönliche "
        "Präferenzen, Projekte oder gespeicherte Fakten relevant sein könnten."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natürlichsprachliche Suchfrage",
            },
            "types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["world", "experience", "observation"],
                },
                "description": "Optionale Faktentypen",
            },
            "budget": {
                "type": "string",
                "enum": ["low", "mid", "high"],
                "description": "Suchumfang",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximale Größe der zurückgegebenen Erinnerungen",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def run(
        self,
        query: str,
        types: list[str] | None = None,
        budget: str = "mid",
        max_tokens: int = 4096,
    ) -> ToolResult:
        payload: dict[str, Any] = {
            "query": query,
            "budget": budget,
            "max_tokens": max_tokens,
        }
        if types:
            payload["types"] = types
        return ToolResult.ok(self.request("memories/recall", payload))


class HindsightRetainTool(HindsightTool):
    name = "memory_retain"
    description = (
        "Speichert wichtige Informationen, Entscheidungen, Präferenzen "
        "und Projektergebnisse dauerhaft in Hindsight. Speichere keine "
        "belanglosen Gesprächsinhalte oder Geheimnisse."
    )
    parameters = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Information, die dauerhaft gespeichert werden soll",
            },
            "context": {
                "type": "string",
                "description": "Kurzer thematischer Kontext, optional",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optionale Tags",
            },
        },
        "required": ["content"],
        "additionalProperties": False,
    }

    def run(
        self,
        content: str,
        context: str | None = None,
        tags: list[str] | None = None,
    ) -> ToolResult:
        item: dict[str, Any] = {"content": content}
        if context:
            item["context"] = context
        if tags:
            item["tags"] = tags
        return ToolResult.ok(
            self.request("memories", {"items": [item], "async": False})
        )
