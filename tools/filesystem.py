"""ODIN Agent - Filesystem Tool.

Erlaubte Dateisystem-Operationen:
  list_directory, read_file, write_file, append_file,
  create_directory, delete_file, move_file, copy_file, search_files

Sicherheit:
  - Zugriff NUR auf konfigurierte erlaubte Roots
    (Standard: /opt/odin-agent, /tmp; erweiterbar via Config).
  - Strikter Path-Traversal-Schutz: jeder Ziel-Pfad wird aufgeloest
    und muss innerhalb eines erlaubten Roots liegen.
  - Klares Ergebnis/Fehlerhandling.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from tools.base import BaseTool, ToolResult

# Stock-Operationen: nicht lesbar/riesig beim list_directory filtern
_IGNORED_NAMES = {".git", "__pycache__", ".venv", "venv", "node_modules"}


class FilesystemTool(BaseTool):
    name = "filesystem"
    description = (
        "Dateisystem-Operationen innerhalb erlaubter Roots. "
        'Aktionen: list_directory, read_file, write_file, append_file, '
        'create_directory, delete_file, move_file, copy_file, search_files. '
        "Gibt den Inhalt/Status der Operation zurueck."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list_directory",
                    "read_file",
                    "write_file",
                    "append_file",
                    "create_directory",
                    "delete_file",
                    "move_file",
                    "copy_file",
                    "search_files",
                ],
                "description": "Die auszufuehrende Dateisystem-Operation.",
            },
            "path": {
                "type": "string",
                "description": "Pfad der Datei/Verzeichnis (relativ zum Root oder absolut).",
            },
            "content": {
                "type": "string",
                "description": "Inhalt fuer write_file/append_file.",
            },
            "destination": {
                "type": "string",
                "description": "Zielpfad fuer move_file/copy_file.",
            },
            "pattern": {
                "type": "string",
                "description": "Suchmuster (Glob) fuer search_files.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, allowed_roots: tuple[str, ...] = ("/opt/odin-agent",)) -> None:
        super().__init__()
        self.allowed_roots = tuple(
            Path(r).resolve() for r in allowed_roots
        )
        # Sicherstellen, dass all erlaubte Roots existieren bzw. anlegbar sind.
        for root in self.allowed_roots:
            root.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # Pfad-Aufloesung + Sicherheit
    # ---------------------------------------------------------

    def _resolve(self, request_path: str | None) -> Path:
        """Loest einen Benutzer-Pfad auf, sichert gegen Traversal ab."""
        if not request_path or not request_path.strip():
            raise ValueError("Pfad fehlt.")
        raw = Path(request_path)
        # Absolut werden, relativ zum ersten Root
        if not raw.is_absolute():
            raw = self.allowed_roots[0] / raw
        try:
            resolved = raw.resolve(strict=False)
        except OSError:
            resolved = raw.absolute()
        return resolved

    def _in_roots(self, resolved: Path) -> bool:
        return any(
            resolved == root or root in resolved.parents
            for root in self.allowed_roots
        )

    def _safe(self, request_path: str | None) -> Path:
        resolved = self._resolve(request_path)
        if not self._in_roots(resolved):
            raise ValueError(
                f"Pfad ausserhalb der erlaubten Verzeichnisse "
                f"({', '.join(str(r) for r in self.allowed_roots)})"
            )
        return resolved

    # ---------------------------------------------------------
    # Aktionen
    # ---------------------------------------------------------

    def _list_directory(self, path: str, recursive: bool = False) -> ToolResult:
        target = self._safe(path)
        if not target.is_dir():
            return ToolResult.fail(error=f"Kein Verzeichnis: {target}")

        def describe(p: Path) -> dict:
            return {
                "name": p.name,
                "path": str(p),
                "type": "dir" if p.is_dir() else "file",
                "size": p.stat().st_size if p.is_file() else None,
            }

        if not recursive:
            items = [
                describe(p)
                for p in sorted(target.iterdir())
                if p.name not in _IGNORED_NAMES
            ]
            return ToolResult.ok(
                data={
                    "path": str(target),
                    "items": items,
                    "count": len(items),
                }
            )
        matches = [
            p
            for p in target.rglob("*")
            if p.name not in _IGNORED_NAMES
        ]
        return ToolResult.ok(
            data={
                "path": str(target),
                "items": [describe(p) for p in matches][:500],
                "count": len(matches),
            }
        )

    def _read_file(self, path: str, max_chars: int = 8000) -> ToolResult:
        target = self._safe(path)
        if not target.is_file():
            return ToolResult.fail(error=f"Keine Datei: {target}")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult.fail(error="Binärdatei/kein UTF-8 — nicht lesbar als Text.")
        except OSError as e:
            return ToolResult.fail(error=f"Lesen fehlgeschlagen: {e}")
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars] + "\n…[gekürzt]"
        return ToolResult.ok(
            data={
                "path": str(target),
                "content": content,
                "truncated": truncated,
            }
        )

    def _write_file(self, path: str, content: str, append: bool = False) -> ToolResult:
        target = self._safe(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            mode = "a" if append else "w"
            with target.open(mode, encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return ToolResult.fail(error=f"Schreiben fehlgeschlagen: {e}")
        return ToolResult.ok(
            data={
                "path": str(target),
                "action": "append" if append else "write",
                "bytes": len(content),
            }
        )

    def _create_directory(self, path: str) -> ToolResult:
        target = self._safe(path)
        if target.exists():
            return ToolResult.ok(data={"path": str(target), "created": False})
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return ToolResult.fail(error=f"Anlegen fehlgeschlagen: {e}")
        return ToolResult.ok(data={"path": str(target), "created": True})

    def _delete_file(self, path: str) -> ToolResult:
        target = self._safe(path)
        if not target.exists():
            return ToolResult.fail(error=f"Pfad existiert nicht: {target}")
        try:
            if target.is_dir():
                target.rmdir()  # nur leere Verzeichnisse räumen
            else:
                target.unlink()
        except OSError as e:
            return ToolResult.fail(error=f"Löschen fehlgeschlagen: {e}")
        return ToolResult.ok(data={"path": str(target), "deleted": True})

    def _move_file(self, path: str, destination: str) -> ToolResult:
        src = self._safe(path)
        dst = self._safe(destination)
        if not src.exists():
            return ToolResult.fail(error=f"Quelle existiert nicht: {src}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except OSError as e:
            return ToolResult.fail(error=f"Verschieben fehlgeschlagen: {e}")
        return ToolResult.ok(
            data={"from": str(src), "to": str(dst), "moved": True}
        )

    def _copy_file(self, path: str, destination: str) -> ToolResult:
        src = self._safe(path)
        dst = self._safe(destination)
        if not src.exists():
            return ToolResult.fail(error=f"Quelle existiert nicht: {src}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
        except OSError as e:
            return ToolResult.fail(error=f"Kopieren fehlgeschlagen: {e}")
        return ToolResult.ok(
            data={"from": str(src), "to": str(dst), "copied": True}
        )

    def _search_files(self, path: str, pattern: str) -> ToolResult:
        target = self._safe(path)
        if not target.is_dir():
            return ToolResult.fail(error=f"Kein Verzeichnis: {target}")
        try:
            matches = list(target.rglob(pattern))
        except OSError as e:
            return ToolResult.fail(error=f"Suche fehlgeschlagen: {e}")
        matches = [
            str(p) for p in matches if p.name not in _IGNORED_NAMES
        ]
        return ToolResult.ok(
            data={"pattern": pattern, "matches": matches[:500], "count": len(matches)}
        )

    # ---------------------------------------------------------
    # Dispatch
    # ---------------------------------------------------------

    def run(
        self,
        action: str,
        path: str | None = None,
        content: str | None = None,
        destination: str | None = None,
        pattern: str | None = None,
    ) -> ToolResult:
        action = (action or "").strip()
        # Alle Aktionen ausser search_files erzwingen einen Pfad.
        if path is None and action != "search_files":
            return ToolResult.fail(error="Pfad fehlt.")
        try:
            if action == "list_directory":
                return self._list_directory(path)
            if action == "read_file":
                return self._read_file(path)
            if action == "write_file":
                if content is None:
                    return ToolResult.fail(error="content fehlt für write_file.")
                return self._write_file(path, content)
            if action == "append_file":
                if content is None:
                    return ToolResult.fail(error="content fehlt für append_file.")
                return self._write_file(path, content, append=True)
            if action == "create_directory":
                return self._create_directory(path)
            if action == "delete_file":
                return self._delete_file(path)
            if action == "move_file":
                if not destination:
                    return ToolResult.fail(error="destination fehlt für move_file.")
                return self._move_file(path, destination)
            if action == "copy_file":
                if not destination:
                    return ToolResult.fail(error="destination fehlt für copy_file.")
                return self._copy_file(path, destination)
            if action == "search_files":
                if not pattern:
                    return ToolResult.fail(error="pattern fehlt für search_files.")
                return self._search_files(path, pattern)
            return ToolResult.fail(error=f"Unbekannte Aktion: {action}")
        except ValueError as e:
            return ToolResult.fail(error=str(e))