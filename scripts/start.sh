#!/usr/bin/env bash
# =========================================================
# ODIN AGENT - Startskript (Web-UI-Adapter, FastAPI/uvicorn)
#
# Startet den ODIN Agent. Laedt Konfiguration aus .env.
# LLM (Bonsai/llama.cpp) wird hier NICHT gestartet - das ist
# ein separater Service. Der Agent verbindet sich nur.
# =========================================================
set -euo pipefail

# Projektwurzel
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

VENV="${PROJECT_DIR}/venv"
PYTHON="${VENV}/bin/python"

# Host/Port aus .env (Fallback 0.0.0.0:8000)
HOST="$(grep -E '^HOST=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || true)"
PORT="$(grep -E '^PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || true)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "[odin-agent] Starte auf ${HOST}:${PORT} (venv: ${PYTHON})"

exec "${VENV}/bin/uvicorn" app:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --app-dir "${PROJECT_DIR}" \
    "$@"