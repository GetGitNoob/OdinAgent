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

        path = self._path(session_id)

        try:

            record = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

        except (OSError, json.JSONDecodeError):

            record = {}

        record["id"] = session_id

        record["messages"] = messages

        self._write(path, record)


    def append_message(self, session_id: str, message: dict) -> list:
        """Haengt eine Nachricht an und gibt die neue Liste zurueck."""
        messages = self.load(session_id)
        messages.append(message)
        self.save(session_id, messages)
        return messages

    def clear(self, session_id: str) -> None:
        self.save(session_id, [])


    def list_chats(self) -> list:
        """Listet alle vorhandenen Chats, sortiert nach letzter Änderung (neueste zuerst).

        Liefert pro gültiger Datei: id, title, updated (ISO-8601).
        Ungültige JSON-Dateien werden übersprungen und protokolliert.
        """
        import logging
        log = logging.getLogger("odin.conversations")
        results = []
        for path in self.data_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                log.warning("list_chats: überspringe %s (%s)", path.name, e)
                continue
            if not isinstance(data, dict):
                continue
            chat_id = data.get("id", path.stem)
            messages = data.get("messages", [])
            # Leere Sessions (z. B. Task-Sessions, deren Worker vor der ersten
            # persistierten Nachricht abgebrochen ist) duerfen keine
            # Sidebar-Eintraege erzeugen.
            if not messages:
                continue
            # Titel bestimmen
            title = data.get("title", "")
            if not title:
                first_user = next(
                    (m.get("content", "") for m in messages
                     if isinstance(m, dict) and m.get("role") == "user"),
                    None
                )
                if first_user:
                    title = first_user[:60] + ("…" if len(first_user) > 60 else "")
                else:
                    title = "Neuer Chat"
            # Letztes Änderungsdatum
            import datetime
            mtime = path.stat().st_mtime
            updated = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
            results.append({"id": chat_id, "title": title, "updated": updated})
        results.sort(key=lambda x: x["updated"], reverse=True)
        return results


    def rename(self, session_id: str, new_title: str) -> bool:
        """Setzt den Titel einer Session dauerhaft."""
        path = self._path(session_id)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        data["title"] = new_title.strip()
        self._write(path, data)
        return True

    def delete(self, session_id: str) -> bool:
        """Löscht die Konversationsdatei dauerhaft. Task-Dateien bleiben erhalten."""
        path = self._path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False


    # ---------------------------------------------------------

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )