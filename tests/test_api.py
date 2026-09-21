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