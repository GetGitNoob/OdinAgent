# ODIN Agent

Lokaler, servernaher KI-Assistent auf dem Server **Odin**. Basiert auf
FastAPI mit Browser-Web-UI (SSE-Streaming) und ist **kanalunabhängig**
aufgebaut: Der Agent Core (Laufschleife + Tools) ist getrennt vom
Kommunikationskanal. So kann später ohne Core-Änderungen ein
WhatsApp-Adapter (Node/wppconnect) hinzukommen.

**Kein Cloud-AI-Dienst** – das LLM läuft auf dem eigenen Server.

## Architektur

```
communication/   (Spaeter: WhatsApp-Node-Adapter; Platzhalter)
agent/
  loop.py        Agent-Kern (Tool-Calling-Relais, Kanal-unabhängig)
  llm.py         LLM-Client (OpenAI-kompatibel, z.B. llama.cpp/Bonsai)
  context.py     Prompt-/History-Aufbereitung
tools/
  base.py        ToolResult, BaseTool, ToolDefinition
  registry.py    Tool-Registry (DI, Factory, Lazy Loading)
  calculator.py  sicherer Rechner (AST-basiert)
  terminal.py    Shell mit Deny-Liste, Timeout, Output-Cap
  filesystem.py  Dateisystem mit Roots + Path-Traversal-Schutz
  system.py      Host/CPU/RAM/Disk/GPU/Uptime/Prozesse
conversation.py  Persistenter Konversations-Store (JSON)
config.py        Konfiguration (frozen dataclass, lädt .env)
app.py           FastAPI-Web-Adapter (SSE, /api/*)
static/          Browser-UI
tests/           pytest-Suite
scripts/         start.sh, install-service.sh
```

### Kanaltrennung
- **Agent Core** (`agent/loop.py`) kennt keine Kanäle. Er bekommt
  `session_id` + Nachricht und liefert `{content, tools, error}`.
- **Adapter** (Browser via `app.py`, später WhatsApp via Node) übersetzen
  Kanal-Protokoll ↔ Agent-API. Der Core bleibt unverändert.

## Schnellstart

```bash
# Abhängigkeiten (einmalig)
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# Konfiguration
cp .env.example .env   # Werte anpassen (LLM, Port, Roots ...)

# Tests
./venv/bin/python -m pytest tests/ -q

# Start (Entwicklung)
./scripts/start.sh
```

## API

| Endpoint          | Beschreibung |
|-------------------|--------------|
| `GET /`           | Browser-UI (statisch) |
| `GET /api/health` | Status (`ok`/`degraded`), LLM-Verfügbarkeit |
| `GET /api/version`| Version (0.4.0) |
| `GET /api/system` | Host/CPU/RAM/Disk/GPU/Uptime/Prozesse |
| `POST /api/chat`  | SSE-Stream: Antwort + Tool-Events |

### Chat-SSE-Protokoll
Jede Zeile ist ein `data: {json}`, Ende mit `data: [DONE]`. Events:
- `{"content": "..."}` – Tokens/Antwort
- `{"type":"tool","tool":"calculator","args":{...}}` – Tool-Aktivität
- `{"error": true, "message": "..."}` – Fehler (LLM offline etc.)

## Sicherheit

- **Terminal-Tool**: immutable Deny-Liste (destruktive Kommandos),
  Timeout, Output-Cap, `approval_required`-Kennzeichnung. Gefährliche
  Aktionen werden blockiert bzw. markiert (späteres Approvalsystem).
- **Filesystem-Tool**: nur erlaubte Roots (Standard `/opt/odin-agent`
  + `/tmp`), strikter Resolve- und Traversal-Check je Operation.
- **Secrets**: nur in `.env` (niemals im Code; `.env` ist gitignored).
- Der Agent startet das LLM/die Dienste **nicht selbst**.

## Systemd-Service

```bash
sudo ./scripts/install-service.sh        # nur installieren
sudo ./scripts/install-service.sh start  # + starten
sudo ./scripts/install-service.sh enable # + Autostart
```

Die Einheit läuft als `berni`, `WorkingDirectory=/opt/odin-agent`.

## Konfiguration (`.env`)

| Variable                  | Bedeutung |
|---------------------------|-----------|
| `LLM_BASE_URL`            | OpenAI-kompatible API (z.B. `http://127.0.0.1:11436/v1`) |
| `LLM_MODEL`               | Modellname |
| `LLM_API_KEY`             | lokaler Key (dummy) |
| `LLM_MAX_TOKENS`          | max. Token pro Antwort |
| `LLM_TEMPERATURE`         | Sampling-Temperatur |
| `MAX_HISTORY_MESSAGES`    | Länge der berücksichtigten Historie |
| `SYSTEM_PROMPT`           | System-Prompt |
| `FILESYSTEM_ALLOWED_ROOTS`| erlaubte Roots (kommagetrennt) |
| `TERMINAL_TIMEOUT`        | Timeout in Sekunden |
| `TERMINAL_MAX_OUTPUT`     | Output-Cap in Zeichen |
| `HOST` / `PORT`           | Bind-Adresse des Webservers |
| `WHATSAPP_ENABLED`        | WhatsApp-Adapter (aktuell false) |

## Status

- [x] Agent Core (Laufschleife, Tools, Persistenz)
- [x] Web-UI-Adapter (SSE, Tool-Events, Health, Version)
- [x] Sicherheit (Terminal-Denyliste, Filesystem-Roots/Traversal)
- [x] Tests (30, pytest)
- [ ] WhatsApp-Adapter (geplant, später)
- [ ] Approvalsystem für gefährliche Aktionen (geplant)