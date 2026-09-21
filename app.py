"""ODIN Agent - FastAPI-Anwendung (Web-UI-Adapter).

Web/SSE-Adapter: liefert die Browser-Oberflaeche und bindet den
Agent Core per HTTP/SSE an. Der Agent Core ist dabei kanalunabhaengig
(AgentLoop), diese Datei ist nur der *Browser-Kanal*.

Endpoints:
  GET  /              -> Browser-UI (static/index.html)
  GET  /api/system    -> GPU-Status (nvidia-smi)
  GET  /api/health    -> Health (LLM verfuegbar/degraded)
  GET  /api/version   -> Versionsinformation
  POST /api/chat      -> SSE-Streaming-Chat (Agent Loop + Tool-Events)
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.llm import LLMClient, LLMError
from config import Config
from conversation import ConversationStore
from tools.registry import get_registry, ToolRegistry
from version import VERSION

# =========================================================
# Dependency-Injection: einmal alle Abhaengigkeiten bauen
# =========================================================

config = Config.load()
conversations = ConversationStore(
    data_dir="/opt/odin-agent/data/conversations"
)
registry: ToolRegistry = get_registry()
llm = LLMClient(config)


def _build_loop():
    from agent.context import AgentContext
    from agent.loop import AgentLoop

    return AgentLoop(
        llm=llm,
        tools=registry,
        conversations=conversations,
        context=AgentContext(config),
    )


# Agent Loop (kanalunabhaengig, wiederverwendbar fuer WhatsApp)
agent = _build_loop()

app = FastAPI(title="Odin Agent", version=VERSION)


# =========================================================
# Pydantic-Modelle
# =========================================================

class ChatRequest(BaseModel):
    message: str
    session_id: str


# =========================================================
# Statische Dateien + Browser-UI
# =========================================================

app.mount(
    "/static",
    StaticFiles(directory="/opt/odin-agent/static"),
    name="static",
)


@app.get("/")
def root():
    return FileResponse("/opt/odin-agent/static/index.html")


# =========================================================
# System-Status (GPU)
# =========================================================

@app.get("/api/system")
def system_status():
    try:
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        temperature, utilization = result.stdout.strip().split(",")
        return {
            "gpu_temperature": int(temperature.strip()),
            "gpu_utilization": int(utilization.strip()),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "gpu_temperature": None,
            "gpu_utilization": None,
            "error": str(e),
        }


# =========================================================
# Health-Check
# =========================================================

@app.get("/api/health")
def health():
    llm_ok = llm.is_configured and llm.check_available()
    return {
        "status": "ok" if llm_ok else "degraded",
        "llm": "available" if llm_ok else "unavailable",
        "version": VERSION,
    }


# =========================================================
# Version
# =========================================================

@app.get("/api/version")
def api_version():
    return {"version": VERSION, "name": "odin-agent"}


# =========================================================
# Streaming Chat (SSE)
# =========================================================

@app.post("/api/chat")
def chat(request: ChatRequest):
    def generate():
        # 1) Tool-Events waehrend/nach Verarbeitung.
        #    AgentLoop liefert erst die komplette Antwort; Tool-Status
        #    wird aus dem Tool-Log als virtuelle "Using ..."-Events gesendet.
        try:
            result = agent.handle_message(
                request.session_id,
                request.message,
            )
        except LLMError as e:
            yield _sse({"error": str(e)})
            yield _sse(None, done=True)
            return
        except Exception as e:  # noqa: BLE001
            yield _sse({"error": str(e)})
            yield _sse(None, done=True)
            return

        # 2) Tool-Events senden (fuer UI "Using calculator/terminal...").
        for tool in result.get("tools", []):
            yield _sse(
                {"type": "tool", "tool": tool["name"], "arguments": tool.get("arguments", {})}
            )

        # 3) Finale Antwort streamen (kompatibel zur bestehenden UI).
        if result.get("error"):
            yield _sse({"error": "Der Agent meldet einen Fehler."})
        elif result.get("content"):
            yield _sse({"content": result["content"]})

        yield _sse(None, done=True)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(data: dict | None, *, done: bool = False) -> str:
    if done:
        return "data: [DONE]\n\n"
    return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"