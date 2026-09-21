"""ODIN Agent - Conversation Store.

Persistenter, JSON-basierter Speicher fuer Konversationen.
Vollstaendig getrennt vom Agent Core: gleiche API fuer Browser/WhatsApp.

Mehrere Sessions ueber session_id (getrennt pro Kanal):
  browser-xxxxx
  whatsapp-xxxxx

Sessions sind strikt getrennt.
"""
from __future__ import annotations

import json
from pathlib import Path


class ConversationStore:
    def __init__(self, data_dir: str = "/opt/odin-agent/data/conversations") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # Hilfen
    # ---------------------------------------------------------

    @staticmethod
    def _sanitize(session_id: str) -> str:
        return "".join(
            c for c in session_id if c.isalnum() or c in "-_"
        )

    def _path(self, session_id: str) -> Path:
        safe = self._sanitize(session_id)
        return self.data_dir / f"{safe}.json"

    # ---------------------------------------------------------
    # API
    # ---------------------------------------------------------

    def load(self, session_id: str) -> list:
        """Liefert die Message-Liste einer Session (leer, wenn neu)."""
        path = self._path(session_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("messages", [])
        except (OSError, json.JSONDecodeError):
            return []

    def get_or_create(self, session_id: str) -> dict:
        """Liefert den gesamten Session-Datensatz."""
        path = self._path(session_id)
        if not path.exists():
            record = {"id": session_id, "messages": []}
            self._write(path, record)
            return record
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("messages", [])
            return data
        except (OSError, json.JSONDecodeError):
            record = {"id": session_id, "messages": []}
            self._write(path, record)
            return record

    def save(self, session_id: str, messages: list) -> None:
        record = {"id": session_id, "messages": messages}
        self._write(self._path(session_id), record)

    def append_message(self, session_id: str, message: dict) -> list:
        """Haengt eine Nachricht an und gibt die neue Liste zurueck."""
        messages = self.load(session_id)
        messages.append(message)
        self.save(session_id, messages)
        return messages

    def clear(self, session_id: str) -> None:
        self.save(session_id, [])

    # ---------------------------------------------------------

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )