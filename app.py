"""ODIN Agent - FastAPI Web/SSE adapter."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import threading
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.llm import LLMClient, LLMError
from config import Config
from conversation import ConversationStore
from tools.registry import get_registry, ToolRegistry
from version import VERSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("odin-agent")

BASE_DIR = Path("/opt/odin-agent")
STATIC_DIR = BASE_DIR / "static"
CONVERSATIONS_DIR = BASE_DIR / "data" / "conversations"
TASKS_DIR = BASE_DIR / "data" / "tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)

config = Config.load()

conversations = ConversationStore(
    data_dir=str(CONVERSATIONS_DIR)
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


agent = _build_loop()

app = FastAPI(
    title="Odin Agent",
    version=VERSION,
)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


@app.on_event("startup")
def _recover_interrupted_tasks():
    """Beim Serverstart: Tasks mit Status queued/running als interrupted markieren."""
    recovered = 0
    for f in TASKS_DIR.glob("*.json"):
        try:
            task = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if task.get("status") in ("queued", "running"):
            task["status"] = "interrupted"
            task["error"] = "Server wurde neu gestartet; Aufgabe konnte nicht fortgesetzt werden."
            f.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
            recovered += 1
    if recovered:
        logger.info("Startup: %d Task(s) als 'interrupted' markiert.", recovered)



class ChatRequest(BaseModel):
    message: str
    session_id: str


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


def _context_status():
    tokens = getattr(agent, "last_prompt_tokens", None)
    limit = 131072
    percent = round(tokens * 100 / limit) if isinstance(tokens, int) else None
    return {"context_tokens": tokens, "context_limit": limit, "context_percent": percent}

@app.get("/api/system")
def system_status():
    """Return current NVIDIA GPU temperature and utilization."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or f"nvidia-smi exit code {result.returncode}"
            logger.warning("nvidia-smi failed: %s", error)
            return {
                "gpu_temperature": None,
                "gpu_utilization": None,
                **_context_status(),
                "error": error,
            }

        line = result.stdout.strip().splitlines()[0].strip()
        parts = [p.strip() for p in line.split(",")]

        if len(parts) != 2:
            raise RuntimeError(f"Unerwartete nvidia-smi-Ausgabe: {line!r}")

        temperature = int(float(parts[0]))
        utilization = int(float(parts[1]))

        return {
            "gpu_temperature": temperature,
            "gpu_utilization": utilization,
            **_context_status(),
        }

    except Exception as exc:
        logger.exception("GPU status failed")
        return {
            "gpu_temperature": None,
            "gpu_utilization": None,
            **_context_status(),
            "error": str(exc),
        }


@app.get("/api/health")
def health():
    try:
        configured = llm.is_configured

        if not configured:
            return {
                "status": "degraded",
                "llm": "unavailable",
                "version": VERSION,
            }

        available = llm.check_available()

        return {
            "status": "ok" if available else "degraded",
            "llm": "available" if available else "unavailable",
            "version": VERSION,
        }

    except Exception as exc:
        logger.exception("Health check failed")
        return {
            "status": "degraded",
            "llm": "unavailable",
            "version": VERSION,
            "error": str(exc),
        }


@app.get("/api/version")
def api_version():
    return {
        "version": VERSION,
        "name": "odin-agent",
    }


@app.get("/api/chats")
def list_chats():
    """Liefert alle vorhandenen Chats (id, title, updated), neueste zuerst."""
    return {"chats": conversations.list_chats()}

@app.put("/api/chats/{chat_id}/rename")
async def rename_chat(chat_id: str, body: dict):
    """Benennt einen Chat um. Body: {"title": "Neuer Titel"}"""
    new_title = body.get("title", "").strip()
    if not new_title or len(new_title) > 200:
        return JSONResponse({"error": "Titel muss 1-200 Zeichen lang sein"}, status_code=400)
    ok = conversations.rename(chat_id, new_title)
    if not ok:
        return JSONResponse({"error": "Chat nicht gefunden"}, status_code=404)
    return {"ok": True, "id": chat_id, "title": new_title}


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """Löscht einen Chat und seine Nachrichtenhistorie dauerhaft."""
    ok = conversations.delete(chat_id)
    if not ok:
        return JSONResponse({"error": "Chat nicht gefunden"}, status_code=404)
    return {"ok": True, "deleted": chat_id}




@app.get("/api/sessions/{session_id}/messages")
def session_messages(session_id: str):
    """Liefert die persistierte Nachrichten-Historie einer Session.

    Dient der Wiederherstellung im Browser (iOS Safari killt beim
    App-Wechsel offene Fetch-Streams; die Antwort liegt aber serverseitig
    in data/conversations/<session>.json). Der Client ruft diesen
    Endpunkt auf, wenn die Seite wieder sichtbar wird oder neu geladen
    wurde, und rendert die Historie neu.
    """
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    if not safe or safe != session_id.strip():
        raise HTTPException(status_code=400, detail="Ungültige Session-ID.")

    messages = conversations.load(safe)
    # Nur stabile Felder an den Client geben (keine internen Tool-Daten).
    public = [
        {"role": m.get("role"), "content": m.get("content", "")}
        for m in messages
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]
    return {"session_id": safe, "messages": public}




# =============================================================
# Task-Verwaltung (asynchrone Chat-Aufgaben)
# =============================================================

_tasks_lock = threading.Lock()


def _task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def _load_task(task_id: str):
    p = _task_path(task_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_task(task: dict) -> None:
    _task_path(task["id"]).write_text(
        json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _find_by_request_id(request_id: str):
    for f in TASKS_DIR.glob("*.json"):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if t.get("request_id") == request_id:
            return t
    return None


class TaskRequest(BaseModel):
    message: str
    session_id: str
    request_id: str


@app.post("/api/tasks", status_code=202)
def start_task(req: TaskRequest):
    """Startet eine asynchrone Chat-Aufgabe. Liefert sofort die task_id.

    Idempotenz: Gleiche request_id liefert denselben Task zurück.
    """
    with _tasks_lock:
        existing = _find_by_request_id(req.request_id)
        if existing:
            return {"task_id": existing["id"], "status": existing["status"], "deduplicated": True}

        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "session_id": req.session_id.strip(),
            "message": req.message.strip(),
            "request_id": req.request_id,
            "status": "queued",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "result": None,
            "error": None,
        }
        _save_task(task)

    # Hintergrund-Thread: Agentenlauf unabhängig von HTTP-Verbindung
    def worker():
        t = _load_task(task_id)
        if not t or t["status"] != "queued":
            return
        t["status"] = "running"
        t["started_at"] = datetime.now().isoformat(timespec="seconds")
        _save_task(t)
        try:
            result = agent.handle_message(t["session_id"], t["message"])
            t = _load_task(task_id)
            t["status"] = "done"
            t["result"] = result.get("content", "")
            t["tools"] = result.get("tools", [])
            t["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _save_task(t)
        except Exception as exc:
            logger.exception("Task %s failed", task_id)
            t = _load_task(task_id)
            t["status"] = "error"
            t["error"] = str(exc)
            t["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _save_task(t)

    th = threading.Thread(target=worker, daemon=True)
    th.start()

    return {"task_id": task_id, "status": "queued", "deduplicated": False}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    """Liefert Status und Ergebnis eines Tasks."""
    safe = "".join(c for c in task_id if c.isalnum() or c in "-_")
    if not safe or safe != task_id.strip():
        raise HTTPException(status_code=400, detail="Ungültige Task-ID.")
    task = _load_task(safe)
    if not task:
        raise HTTPException(status_code=404, detail="Task nicht gefunden.")
    return task


@app.post("/api/chat")
def chat(request: ChatRequest):
    def generate():
        message = request.message.strip()
        session_id = request.session_id.strip()

        if not message:
            yield _sse({"error": "Leere Nachricht."})
            yield _sse(None, done=True)
            return

        if not session_id:
            yield _sse({"error": "Keine Session-ID."})
            yield _sse(None, done=True)
            return

        logger.info(
            "Chat request session=%s message=%r",
            session_id,
            message[:200],
        )

        try:
            result = agent.handle_message(
                session_id,
                message,
            )

            logger.info(
                "Agent result session=%s keys=%s",
                session_id,
                list(result.keys()) if isinstance(result, dict) else type(result).__name__,
            )

        except LLMError as exc:
            logger.exception(
                "LLM error during chat session=%s",
                session_id,
            )
            yield _sse({
                "error": str(exc),
            })
            yield _sse(None, done=True)
            return

        except Exception as exc:
            logger.exception(
                "Agent error during chat session=%s",
                session_id,
            )
            yield _sse({
                "error": f"Agent-Fehler: {exc}",
            })
            yield _sse(None, done=True)
            return

        if not isinstance(result, dict):
            logger.error(
                "Agent returned invalid result: %r",
                result,
            )
            yield _sse({
                "error": "Ungültige Antwort vom Agent Core.",
            })
            yield _sse(None, done=True)
            return

        if result.get("error"):
            error = result.get("error")

            logger.error(
                "Agent returned error session=%s: %s",
                session_id,
                error,
            )

            yield _sse({
                "error": str(error),
            })
            yield _sse(None, done=True)
            return

        for tool in result.get("tools", []) or []:
            if not isinstance(tool, dict):
                continue

            yield _sse({
                "type": "tool",
                "tool": tool.get("name", "unknown"),
                "arguments": tool.get("arguments", {}),
            })

        content = result.get("content")

        if content is not None:
            yield _sse({
                "content": str(content),
            })
        else:
            logger.warning(
                "Agent returned no content session=%s result=%r",
                session_id,
                result,
            )
            yield _sse({
                "error": "Der Agent hat keine Antwort erzeugt.",
            })

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

    return (
        "data: "
        + json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n\n"
    )
