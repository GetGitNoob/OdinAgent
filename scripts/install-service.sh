#!/usr/bin/env bash
# =========================================================
# ODIN AGENT - Installiert den systemd-Service.
#
# Setzt den richtigen User/Pfad und installiert die Einheit
# unter /etc/systemd/system/odin-agent.service.
# Nutzt sudo (passwortlos auf diesem Server).
#
#   sudo ./scripts/install-service.sh [start|enable]
#   - (kein Arg): nur installieren
#   - start:      zusaetzlich starten
#   - enable:     zusaetzlich beim Boot aktivieren
# =========================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Unter sudo den eigentlichen User verwenden, nicht root.
RUN_USER="${SUDO_USER:-$USER}"
SERVICE_FILE="/etc/systemd/system/odin-agent.service"

echo "[install-service] Projekt:   ${PROJECT_DIR}"
echo "[install-service] User:      ${RUN_USER}"
echo "[install-service] Einheit:   ${SERVICE_FILE}"

# Host/Port mit Fallback (funktioniert auch ohne .env)
APP_HOST="$("${PROJECT_DIR}"/venv/bin/python -c 'from config import Config; print(Config.load().host)' 2>/dev/null || echo 0.0.0.0)"
APP_PORT="$("${PROJECT_DIR}"/venv/bin/python -c 'from config import Config; print(Config.load().port)' 2>/dev/null || echo 8000)"

echo "[install-service] Host:      ${APP_HOST}"
echo "[install-service] Port:      ${APP_PORT}"

# -------------------- Unit-Datei erzeugen --------------------
TMP_UNIT="$(mktemp)"
cat > "${TMP_UNIT}" <<EOF
[Unit]
Description=ODIN Agent (Web-UI-Adapter, FastAPI/SSE)
After=network.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_USER}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/venv/bin/uvicorn app:app --host ${APP_HOST} --port ${APP_PORT} --app-dir ${PROJECT_DIR}
Restart=on-failure
RestartSec=3
# Nicht das ganze System killen, nur den Agent-Prozess
KillMode=mixed
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 644 "${TMP_UNIT}" "${SERVICE_FILE}"
rm -f "${TMP_UNIT}"
sudo systemctl daemon-reload

echo "[install-service] OK: Einheit installiert."

case "${1:-}" in
  start)
    sudo systemctl restart odin-agent
    sudo systemctl --no-pager status odin-agent --lines=0 || true
    ;;
  enable)
    sudo systemctl enable odin-agent
    echo "[install-service] OK: Autostart aktiviert."
    ;;
esac

echo "[install-service] Fertig."