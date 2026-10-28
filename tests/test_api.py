"""API-Tests fuer die FastAPI-Anwendung (TestClient + Mock)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:1/v1")

from fastapi.testclient import TestClient  # noqa: E402

import app as appmod  # noqa: E402


@pytest.fixture
def client():
    return TestClient(appmod.app)


def test_version_endpoint(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.json()["version"] == "0.2.0"


def test_health_degraded(client, monkeypatch):
    monkeypatch.setattr(appmod.llm, "check_available", lambda: False)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["llm"] == "unavailable"


def test_health_ok(client, monkeypatch):
    monkeypatch.setattr(appmod.llm, "check_available", lambda: True)
    r = client.get("/api/health")
    assert r.json()["status"] == "ok"
    assert r.json()["llm"] == "available"


def test_root_serves_ui(client):
    r = client.get("/")
    assert r.status_code == 200


def test_chat_stream_with_tool_events(client, monkeypatch):
    class FakeAgent:
        def handle_message(self, session_id, message):
            return {
                "content": "Die Antwort ist 42.",
                "tools": [
                    {"name": "calculator", "arguments": {"expression": "6*7"}}
                ],
                "error": False,
            }

    monkeypatch.setattr(appmod, "agent", FakeAgent())
    r = client.post(
        "/api/chat",
        json={"message": "Berechne 6*7", "session_id": "browser-api-test"},
    )
    assert r.status_code == 200
    text = r.text
    assert "calculator" in text       # Tool-Event vorhanden
    assert "Die Antwort ist 42" in text
    assert "[DONE]" in text


def test_chat_stream_llm_error(client, monkeypatch):
    class ErrorAgent:
        def handle_message(self, session_id, message):
            from agent.llm import LLMError

            raise LLMError("Offline")

    monkeypatch.setattr(appmod, "agent", ErrorAgent())
    r = client.post(
        "/api/chat",
        json={"message": "hi", "session_id": "browser-api-err"},
    )
    assert '"error"' in r.text


# ---------------------------------------------------------
# Session-History-Endpoint (iOS-Safari-Recovery)
# ---------------------------------------------------------

def test_session_messages_endpoint(client, monkeypatch):
    # Persistierte Historie direkt im ConversationStore anlegen
    # (gleicher Store, den app.py verwendet).
    appmod.conversations.save(
        "browser-history-test",
        [
            {"role": "user", "content": "Frage 1"},
            {"role": "assistant", "content": "Antwort A"},
        ],
    )

    r = client.get("/api/sessions/browser-history-test/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "browser-history-test"
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant"]
    assert body["messages"][0]["content"] == "Frage 1"
    assert body["messages"][1]["content"] == "Antwort A"


def test_session_messages_unknown_session_returns_empty(client):
    r = client.get("/api/sessions/nicht-existierend-xyz/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["messages"] == []


def test_session_messages_rejects_invalid_id(client):
    # Pfadtraversal / Sonderzeichen werden abgewiesen.
    r = client.get("/api/sessions/..%2Fetc%2Fshadow/messages")
    assert r.status_code in (400, 404)


# ---------------------------------------------------------
# Task-Live-Zwischenstaende (v0.4.0)
# ---------------------------------------------------------

def _wait_for_task(client, task_id, timeout_s=10.0):
    """Wartet bis der Hintergrund-Worker den Task abgeschlossen hat.

    Liest die Task-JSON direkt aus dem (getesteten) TASKS_DIR – so ist
    der Test unabhaengig davon, ob der Worker-Thread im TestClient-Kontext
    synchron oder asynchron laeuft.
    """
    import json as _json
    import time as _time

    deadline = _time.monotonic() + timeout_s
    path = appmod.TASKS_DIR / (task_id + ".json")
    while _time.monotonic() < deadline:
        if path.exists():
            try:
                data = _json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = None
            if data and data.get("status") in ("done", "error", "interrupted"):
                # API-Endpunkt muss denselben Zustand liefern
                r = client.get("/api/tasks/" + task_id)
                assert r.status_code == 200
                assert r.json()["status"] == data["status"]
                return data
        _time.sleep(0.05)
    raise AssertionError("Task wurde nicht rechtzeitig fertig: " + task_id)


def test_task_updates_persisted_and_capped(client, monkeypatch, tmp_path):
    """on_event-Ereignisse landen thread-sicher in der Task-JSON (max. 50)."""
    # Tasks in ein Testverzeichnis umleiten
    from pathlib import Path as _P
    tasks_dir = _P(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appmod, "TASKS_DIR", tasks_dir)

    class UpdateAgent:
        def handle_message(self, session_id, message, on_event=None):
            for i in range(60):
                if on_event is not None:
                    on_event({"type": "tool_start", "name": f"t{i}"})
            return {"content": "fertig", "tools": [], "error": False}

    monkeypatch.setattr(appmod, "agent", UpdateAgent())

    r = client.post(
        "/api/tasks",
        json={
            "message": "langlaufend",
            "session_id": "task-updates-test",
            "request_id": "req-updates-1",
        },
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]

    data = _wait_for_task(client, task_id)
    assert data["status"] == "done"
    assert data["result"] == "fertig"

    updates = data.get("updates", [])
    # Liste ist auf MAX_TASK_UPDATES=50 begrenzt (letzte 50 von 60)
    assert len(updates) == appmod.MAX_TASK_UPDATES == 50
    assert all(u["type"] == "tool_start" for u in updates)
    assert updates[0]["name"] == "t10"   # die ersten 10 wurden verdrängt
    assert updates[-1]["name"] == "t59"
    # Jeder Eintrag hat einen Zeitstempel
    assert all("ts" in u for u in updates)


def test_task_updates_not_in_conversation_history(client, monkeypatch, tmp_path):
    """Zwischenstaende duerfen NICHT als Chat-Nachrichten persistiert werden."""
    from pathlib import Path as _P
    tasks_dir = _P(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appmod, "TASKS_DIR", tasks_dir)

    class UpdateAgent:
        def handle_message(self, session_id, message, on_event=None):
            # Wie der echte AgentLoop: user-Eingang + finale assistant-Antwort
            # werden im ConversationStore persistiert (je genau einmal).
            existing = appmod.conversations.load(session_id) or []
            if not any(m.get("role") == "user" and m.get("content") == message for m in existing):
                appmod.conversations.append_message(session_id, {"role": "user", "content": message})
            if on_event is not None:
                on_event({"type": "tool_start", "name": "geheimer-zwischenstand"})
            if not any(m.get("role") == "assistant" and m.get("content") == "Finale Antwort." for m in existing):
                appmod.conversations.append_message(
                    session_id, {"role": "assistant", "content": "Finale Antwort."}
                )
            return {"content": "Finale Antwort.", "tools": [], "error": False}

    monkeypatch.setattr(appmod, "agent", UpdateAgent())

    r = client.post(
        "/api/tasks",
        json={
            "message": "Frage mit Zwischenstand",
            "session_id": "task-conv-test",
            "request_id": "req-conv-1",
        },
    )
    task_id = r.json()["task_id"]
    data = _wait_for_task(client, task_id)
    assert data["status"] == "done"
    # Der Zwischenstand steht in der Task-JSON …
    assert any(
        u.get("name") == "geheimer-zwischenstand" for u in data.get("updates", [])
    )

    # … aber NICHT im Gesprächsverlauf (nur user/assistant, finale Antwort einmalig)
    hist = appmod.conversations.load("task-conv-test")
    roles = [m["role"] for m in hist]
    assert roles.count("user") == 1
    assert roles.count("assistant") == 1
    contents = [m["content"] for m in hist]
    assert "Finale Antwort." in contents
    assert "geheimer-zwischenstand" not in " ".join(contents)

    # Auch das API-Endpoint liefert nur user/assistant
    r2 = client.get("/api/sessions/task-conv-test/messages")
    assert r2.status_code == 200
    body = r2.json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]


def test_task_without_updates_field_still_works(client, monkeypatch, tmp_path):
    """Alte Task-JSONs ohne 'updates'-Feld bleiben lesbar und lauffaehig."""
    from pathlib import Path as _P
    tasks_dir = _P(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appmod, "TASKS_DIR", tasks_dir)

    # Alte Task ohne updates-Feld manuell anlegen
    old_task = {
        "id": "old-task-123",
        "session_id": "alt",
        "message": "alt",
        "request_id": "req-old-1",
        "status": "queued",
        "created_at": "2026-01-01T00:00:00",
        "result": None,
        "error": None,
    }
    (tasks_dir / "old-task-123.json").write_text(
        __import__("json").dumps(old_task), encoding="utf-8"
    )

    class QuietAgent:
        def handle_message(self, session_id, message, on_event=None):
            return {"content": "ok", "tools": [], "error": False}

    monkeypatch.setattr(appmod, "agent", QuietAgent())

    r = client.post(
        "/api/tasks",
        json={"message": "neu", "session_id": "alt", "request_id": "req-new-1"},
    )
    task_id = r.json()["task_id"]
    data = _wait_for_task(client, task_id)
    assert data["status"] == "done"

    # Die alte Task bleibt unverändert lesbar (kein updates-Feld nötig)
    r_old = client.get("/api/tasks/old-task-123")
    assert r_old.status_code == 200
    assert "updates" not in r_old.json()


def test_empty_task_session_creates_no_sidebar_entry(client, monkeypatch, tmp_path):
    """Zwischenstaende/Task-Sessions duerfen keine neuen Chats erzeugen.

    Reproduziert den v0.4.0-UI-Fehler: Der AgentLoop legt ueber
    get_or_create() sofort eine Session-Datei an. Crasht der Worker vor
    der ersten persistierten Nachricht (z. B. LLM-Timeout), blieb die
    leere Datei zurueck und list_chats() zeigte sie als 'Neuer Chat' in
    der Sidebar. Leere Sessions muessen gefiltert werden.
    """
    from pathlib import Path as _P
    tasks_dir = _P(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appmod, "TASKS_DIR", tasks_dir)

    # Bestehender Chat mit Inhalt bleibt sichtbar
    appmod.conversations.append_message(
        "sidebar-test-alt", {"role": "user", "content": "Frage 1"}
    )

    class CrashingAgent:
        def handle_message(self, session_id, message, on_event=None):
            # Wie der echte AgentLoop: Session wird angelegt ...
            appmod.conversations.get_or_create(session_id)
            if on_event is not None:
                on_event({"type": "llm_start", "round": 1})
            # ... dann crasht der Worker vor der ersten append_message
            raise RuntimeError("LLM nicht erreichbar")

    monkeypatch.setattr(appmod, "agent", CrashingAgent())

    r = client.post(
        "/api/tasks",
        json={
            "message": "Frage mit Zwischenstand",
            "session_id": "sidebar-test-neu",
            "request_id": "req-sidebar-1",
        },
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]
    data = _wait_for_task(client, task_id)
    assert data["status"] == "error"
    # Der Zwischenstand wurde protokolliert ...
    assert any(u["type"] == "llm_start" for u in data.get("updates", []))

    # ... aber die leere Task-Session erzeugt KEINEN Sidebar-Eintrag
    chats = {c["id"]: c for c in appmod.conversations.list_chats()}
    assert "sidebar-test-alt" in chats, "Bestehender Chat darf nicht verschwinden"
    assert "sidebar-test-neu" not in chats, "Leere Task-Session taucht in der Sidebar auf"

    # Auch ueber das API-Endpunkt
    r2 = client.get("/api/chats")
    assert r2.status_code == 200
    ids = [c["id"] for c in r2.json()["chats"]]
    assert "sidebar-test-neu" not in ids
    assert "sidebar-test-alt" in ids


def test_task_timestamps_are_naive_local_iso(client, monkeypatch, tmp_path):
    """Task-Zeitstempel sind naive lokale ISO-Zeiten (keine UTC-Markierung).

    Der Browser parst started_at als lokale Zeit und leitet daraus einen
    stabilen Timer-Basiswert ab. Waere der Server auf UTC ("Z"-Suffix)
    umgestellt, muesste die Client-Seite mitziehen – dieser Test sichert
    das gemeinsame Format ab.
    """
    from pathlib import Path as _P
    tasks_dir = _P(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appmod, "TASKS_DIR", tasks_dir)

    class QuietAgent:
        def handle_message(self, session_id, message, on_event=None):
            return {"content": "ok", "tools": [], "error": False}

    monkeypatch.setattr(appmod, "agent", QuietAgent())

    r = client.post(
        "/api/tasks",
        json={
            "message": "Zeitformat-Test",
            "session_id": "task-ts-test",
            "request_id": "req-ts-1",
        },
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]
    data = _wait_for_task(client, task_id)

    for field in ("created_at", "started_at", "finished_at"):
        value = data.get(field)
        assert value, f"{field} fehlt in der Task-JSON"
        # Naive lokale Zeit: kein Z-Suffix, keine Offset-Angabe
        assert not value.endswith("Z"), f"{field} ist UTC-markiert: {value}"
        # Naive Zeit: kein "+HH:MM"-Offset nach dem "T"
        assert "T" in value and "+" not in value.split("T", 1)[1], (
            f"{field} enthaelt ein UTC-Offset: {value}"
        )
        # Muss parsbar sein (ISO-8601, Sekunden-Praezision)
        from datetime import datetime
        datetime.fromisoformat(value)

    # Updates tragen dasselbe Zeitstempel-Format
    for update in data.get("updates", []):
        assert not update["ts"].endswith("Z")


def test_status_updates_create_no_new_chats(client, monkeypatch, tmp_path):
    """Live-Zwischenstaende duerfen weder neue Chats noch Sidebar-Eintraege
    erzeugen; die finale Antwort landet genau einmal im urspruenglichen Chat.

    Ergaenzt den Sidebar-Filter-Test: hier wird der komplette Pfad
    ueberprueft – Task-Start, mehrere Zwischenstaende, Abschluss – und
    verifiziert, dass die Session-Zuordnung (task.session_id) erhalten
    bleibt und /api/chats nur den urspruenglichen Chat kennt.
    """
    from pathlib import Path as _P
    tasks_dir = _P(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appmod, "TASKS_DIR", tasks_dir)

    # Test-Isolation: Session-Store in ein frisches Verzeichnis umleiten,
    # damit echte Chats aus data/conversations nicht mitgezählt werden.
    from conversation import ConversationStore as _CS
    conv_dir = _P(tmp_path) / "conv"
    conv_dir.mkdir(parents=True, exist_ok=True)
    store = _CS(data_dir=str(conv_dir))
    monkeypatch.setattr(appmod, "conversations", store)

    # Vorheriger Stand: genau ein Chat existiert
    store.append_message("status-chats-alt", {"role": "user", "content": "Frage 1"})
    before_ids = {c["id"] for c in store.list_chats()}
    assert before_ids == {"status-chats-alt"}

    class StatusAgent:
        def handle_message(self, session_id, message, on_event=None):
            # Wie der echte AgentLoop: user-Nachricht persistieren ...
            appmod.conversations.append_message(
                session_id, {"role": "user", "content": message}
            )
            # ... dann Live-Zwischenstaende feuern (nur an die UI, nie in den Store)
            if on_event is not None:
                on_event({"type": "llm_start", "round": 1})
                on_event({"type": "tool_start", "name": "terminal"})
                on_event({
                    "type": "tool_done",
                    "name": "terminal",
                    "success": True,
                    "duration": 90.0,
                })
                on_event({"type": "llm_start", "round": 2})
            # Finale Antwort genau einmal persistieren
            appmod.conversations.append_message(
                session_id, {"role": "assistant", "content": "fertig"}
            )
            return {"content": "fertig", "tools": [], "error": False}

    monkeypatch.setattr(appmod, "agent", StatusAgent())

    r = client.post(
        "/api/tasks",
        json={
            "message": "Frage mit Zwischenstand",
            "session_id": "status-chats-neu",
            "request_id": "req-status-1",
        },
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]
    data = _wait_for_task(client, task_id)
    assert data["status"] == "done"
    assert data["result"] == "fertig"

    # Task-Zuordnung bleibt erhalten
    assert data["session_id"] == "status-chats-neu"

    # Zwischenstaende stehen in der Task-JSON (mit ts + Dauer) ...
    types = [u["type"] for u in data.get("updates", [])]
    assert types == ["llm_start", "tool_start", "tool_done", "llm_start"], types
    done = next(u for u in data["updates"] if u["type"] == "tool_done")
    assert done["duration"] == 90.0
    assert all("ts" in u for u in data["updates"])

    # ... aber es gibt genau zwei Chats: alt + neu (kein dritter Eintrag)
    after = store.list_chats()
    after_ids = {c["id"] for c in after}
    # Genau ein neuer Eintrag: der Chat der Task. Keine Phantom-Chats.
    new_ids = after_ids - before_ids
    assert new_ids == {"status-chats-neu"}, (before_ids, after_ids)

    # API liefert denselben Zustand
    r2 = client.get("/api/chats")
    assert r2.status_code == 200
    api_ids = {c["id"] for c in r2.json()["chats"]}
    assert api_ids - before_ids == {"status-chats-neu"}

    # Finale Antwort erscheint genau einmal im urspruenglichen Chat
    hist = store.load("status-chats-neu")
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert hist[1]["content"] == "fertig"
    assert sum(1 for m in hist if m["content"] == "fertig") == 1
