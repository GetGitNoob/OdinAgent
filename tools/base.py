"""ODIN Agent - Tool-Basis.

Definiert:
  - ToolResult   : strukturiertes, serialisierbares Tool-Ergebnis.
  - BaseTool     : Interface, das jedes Tool implementiert.
  - ToolDefinition: OpenAI-kompatible Schema-Beschreibung.

Tools liefern NIE unkontrollierte Python-Exceptions bis zum
Browser/WhatsApp durch. Jede Ausfuehrung endet in einem ToolResult.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    """Strukturiertes Tool-Ergebnis.

    Erfolg:   success=True,  data=<wert>
    Fehler:   success=False, error=<nachricht>
    Zusaetzlich: duration (s), approval_required (Sicherheits-Flag).
    """

    success: bool
    data: Any = None
    error: str | None = None
    duration: float = 0.0
    approval_required: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration": round(self.duration, 4),
            "approval_required": self.approval_required,
        }

    def __str__(self) -> str:
        """Kompakte, LLM-freundliche Darstellung (Kontext-schoend).

        Bei Fehlern wird die konkrete Fehlermeldung ausgegeben,
        niemals ein Boolean als Ersatz.
        """
        if not self.success:
            parts = [f"FEHLER: {self.error or 'unbekannter Fehler'}"]
            if self.approval_required:
                parts.append("(Zustimmung erforderlich)")
            return " ".join(parts)
        import json

        try:
            return json.dumps(self.data, ensure_ascii=False)[:4000]
        except Exception:
            return str(self.data)[:4000]

    @classmethod
    def ok(cls, data: Any = None, duration: float = 0.0) -> "ToolResult":
        return cls(success=True, data=data, duration=duration)

    @classmethod
    def fail(
        cls,
        error: str,
        duration: float = 0.0,
        approval_required: bool = False,
    ) -> "ToolResult":
        return cls(
            success=False,
            error=error,
            duration=duration,
            approval_required=approval_required,
        )


class BaseTool:
    """Interface fuer ein Odin-Tool.

    Unterklassen muessen implementieren:
      name, description, parameters (OpenAI-Schema)
      run(...)  -> ToolResult

    Die `definition`-Property liefert das komplette
    OpenAI-kompatible Tool-Objekt fuer das LLM.
    """

    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)
    func: Callable | None = None

    def __init__(self) -> None:
        if not self.name or not self.description:
            raise ValueError(
                f"Tool {type(self).__name__}: name/description fehlt"
            )

    @property
    def definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError(f"Tool {self.name}: run() nicht implementiert")

    def execute(self, arguments: dict) -> ToolResult:
        """Fuehrt das Tool mit Argumenten aus und faengt alle Fehler.

        Darf NIE eine Exception werfen -> gibt immer ToolResult zurueck.
        """
        import time

        start = time.perf_counter()
        try:
            result = self.run(**arguments)
            if not isinstance(result, ToolResult):
                result = ToolResult(success=True, data=result)
        except TypeError as e:
            result = ToolResult.fail(
                error=f"Parameter-Fehler: {e}",
                duration=time.perf_counter() - start,
            )
        except Exception as e:  # noqa: BLE001
            result = ToolResult.fail(
                error=f"{type(e).__name__}: {e}",
                duration=time.perf_counter() - start,
            )
        result.duration = time.perf_counter() - start
        return result