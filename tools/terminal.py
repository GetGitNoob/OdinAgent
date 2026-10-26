"""ODIN Agent - Terminal Tool.

Fuehrt Shell-Befehle aus. Sicherheitsmerkmale:
  - Timeout (Standard TERMINAL_TIMEOUT, kein endloses Blockieren)
  - Output-Cap (Standard TERMINAL_MAX_OUTPUT, mit "[output truncated]")
  - Harte Deny-Liste fuer potenziell destruktive/gefaehrliche Befehle
  - Saubere Fehlerbehandlung + strukturierte Ergebnisse
  - Optionales Working Directory (nur, wenn angegeben + existiert)

Der LLM darf NICHT unkontrolliert Systeme zerstoeren. Die Deny-Liste
ist immutable und laeuft NICHT ueber Config umgehbar.
"""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

from tools.base import BaseTool, ToolResult

# ---------------------------------------------------------
# Harte Deny-Liste (immutable). Erweitern, wenn nötig.
# Jeder Eintrag ist ein Regex (re.I) der auf den Befehl gematcht wird.
# ---------------------------------------------------------
_DENY_PATTERNS: tuple[str, ...] = (
    # Destruktive Dateisystem-Operationen (rm mit -r und/oder -f auf Root)
    #  -> '/', '/*' oder '.*  am Ende', blocken.
    r"\brm\s+(?:-[a-zA-Z]*[rf][a-zA-Z]*\s+)*(?:/\*|/\s|/$|\\.|/.)",
    r"\bmkfs",  # Formatierung
    r"\bdd\s+if=.*of=/\s*dev/",  # auf rohe Geraete schreiben
    r"\bshred\s+.*/\s*dev/",
    # System-Abschaltung / Neustart
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bhalt\b",
    r"\binit\s+0\b",
    r"\binit\s+6\b",
    # Kritische Dienste kapern
    r"\bsystemctl\s+(?:stop|disable|mask|kill|poweroff|halt|reboot)\b",
    r"\bservice\s+\S+\s+stop\b",
    # Root-Kennwort / Passwd aendern
    r"\bpasswd\b",
    r"\bchpasswd\b",
    # Container roh entfernen
    r"\bdocker\s+(?:rm\s+-f|image\s+rm\s+-f|volume\s+rm\s+-f)\b",
    r"\bpodman\s+(?:rm\s+-f)\b",
    # Berechtigungen pauschal auf Wurzel
    r"\bchmod\s+-R\s+777\s+/",
    r"\bchown\s+-R\s+\S+\s+/",
)


class TerminalTool(BaseTool):
    name = "terminal"
    description = (
        "Fuehrt einen Shell-Befehl aus und liefert stdout/stderr/exit_code/duration. "
        "Fuer System-Informationen, Datei-Operationen oder Inspektionen. "
        "Output ist begrenzt, destruktive Befehle sind blockiert."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Der auszufuehrende Shell-Befehl.",
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Maximale Laufzeit in Sekunden (optional, default aus Config)."
                ),
            },
            "working_dir": {
                "type": "string",
                "description": "Working Directory (optional).",
            },
        },
        "required": ["command"],
    }

    def __init__(self, timeout: int = 10, max_output: int = 10_000) -> None:
        super().__init__()
        self.default_timeout = timeout
        self.max_output = max_output

    def _is_denied(self, command: str) -> str | None:
        for pattern in _DENY_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return pattern
        return None

    def run(
        self,
        command: str,
        timeout: int | None = None,
        working_dir: str | None = None,
    ) -> ToolResult:
        if not command or not command.strip():
            return ToolResult.fail(error="Kein Befehl angegeben.")

        # --- Sicherheits-Check: Deny-Liste -------------------
        denied_match = self._is_denied(command)
        if denied_match:
            return ToolResult.fail(
                error=(
                    f"Befehl durch Sicherheitsrichtlinie blockiert "
                    f"(Muster: {denied_match}). Zustimmung erforderlich."
                ),
                approval_required=True,
            )

        cmd_timeout = (
            timeout if timeout and timeout > 0 else self.default_timeout
        )

        cwd = None
        if working_dir:
            cwd = Path(working_dir)
            if not cwd.is_dir():
                return ToolResult.fail(
                    error=f"Working-Directory existiert nicht: {working_dir}"
                )

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=cmd_timeout,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired as e:
            # Partial-Output kann vorhanden sein (stdout/stderr des abgebrochenen Prozes)
            partial_stdout = ""
            partial_stderr = ""
            if hasattr(e, "stdout") and e.stdout:
                partial_stdout = e.stdout if isinstance(e.stdout, str) else e.stdout.decode(errors="replace")
            if hasattr(e, "stderr") and e.stderr:
                partial_stderr = e.stderr if isinstance(e.stderr, str) else e.stderr.decode(errors="replace")
            detail = (
                f"Timeout nach {cmd_timeout}s (subprocess.TimeoutExpired). "
                f"Befehl: {command!r}. "
                f"Nicht innerhalb der Zeit beendet (evtl. interaktiv/blockierend)."
            )
            if partial_stdout:
                detail += f" Partial-stdout: {partial_stdout[:500]}"
            if partial_stderr:
                detail += f" Partial-stderr: {partial_stderr[:500]}"
            return ToolResult.fail(error=detail)
        except FileNotFoundError as e:
            # e.msg enthaelt typischerweise den fehlenden Pfad/Befehl
            msg = getattr(e, "msg", None) or str(e)
            return ToolResult.fail(
                error=(
                    f"FileNotFoundError: Befehl nicht gefunden: {msg} "
                    f"(Befehl war: {command!r})"
                )
            )
        except PermissionError as e:
            msg = getattr(e, "msg", None) or str(e)
            return ToolResult.fail(
                error=(
                    f"PermissionError: Keine Berechtigung: {msg} "
                    f"(Befehl war: {command!r})"
                )
            )
        except OSError as e:
            return ToolResult.fail(
                error=(
                    f"OSError ({e.errno}): {e.strerror or e} "
                    f"(Befehl war: {command!r})"
                )
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult.fail(
                error=f"{type(e).__name__}: {e} (Befehl war: {command!r})"
            )

        # --- Output kuerzen -------------------------------
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        stdout_truncated = len(stdout) > self.max_output
        stderr_truncated = len(stderr) > self.max_output
        if stdout_truncated:
            stdout = stdout[: self.max_output] + "\n[output truncated]"
        if stderr_truncated:
            stderr = stderr[: self.max_output] + "\n[output truncated]"

        exit_code = proc.returncode

        # Nicht-null Exit-Code: Der Befehl lief aus, aber fehlerhaft.
        # Wir liefern das Ergebnis trotzdem (mit exit_code), damit der
        # Aufrufer (LLM) selbst entscheiden kann, ob es ein Problem ist.
        # Zusätzlich kennzeichnen wir es, falls stderr vorhanden ist.
        data = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "truncated": stdout_truncated or stderr_truncated,
        }

        if exit_code != 0:
            # Klare Kennzeichnung, dass der Befehl fehlerhaft endete
            hint = f"[exit_code={exit_code}]"
            if stderr:
                data["note"] = (
                    f"Befehl endete mit Exit-Code {exit_code}. "
                    f"stderr: {stderr[:500]}"
                )
            else:
                data["note"] = (
                    f"Befehl endete mit Exit-Code {exit_code} (kein stderr)."
                )

        return ToolResult.ok(data=data)
