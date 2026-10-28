# Changelog

## v0.4.0 – Hindsight-Reparatur, LLM-Timeouts, Systemd-Units

### Neue Features
- **Systemd-Units im Repo:** `systemd/`-Verzeichnis mit `hindsight.service`, `pg0-hindsight.service`, `odin-agent.service`, `ninfer.service` – vollständige Deployment-Konfiguration.
- **LLM-Timeouts granular:** Getrennte httpx-Timeouts (connect=10s, read=600s, write=60s, pool=30s) statt flacher 120s – lange Generierungen crashen nicht mehr.
- **reasoning_effort:** `medium` als Default für Qwen3.8-27B via NInfer.

### Fehlerbehebungen
- **Hindsight/pg0-Reparatur:** Shared-Memory-Crash behoben durch `LD_LIBRARY_PATH`-Setting in `pg0-hindsight.service` (libicuuc.so.70 aus pg0-Installation).
- **Timer-Fix (100ms-Tick):** Zwischenstands-Events in der WebUI werden jetzt flüssig aktualisiert.
- **Test-Isolation:** Tests laufen unabhängig voneinander, keine Cross-Contamination mehr.

### Änderungen
- System-Prompt erweitert (Ehrlichkeit, Humor, experimenteller Charakter).
- `.gitignore` ergänzt (Backup-Dateien, HA-Konfiguration).

## v0.3.0 – Stabile Version

### Neue Features
- **Web-Suche & -Recherche:** Neue Tools `web_search` und `web_research` für aktuelle Internetinformationen.
- **Bildanalyse:** Neues Tool `image_analysis` (Qwen-Vision via NInfer-API) zur visuellen Bildauswertung.
- **Hindsight-Memory:** Native Hindsight-Tools (`memory_recall`, `memory_retain`) für persistente Wissensspeicherung.
- **Kopierbuttons:** Jede Odin-Antwort erhält einen Kopierbutton (Clipboard-API + Fallback), der den vollständigen Antworttext kopiert.
- **Chat-Umbenennen/-Löschen:** Funktionierende ✎/✕-Buttons in der Sidebar mit PUT/DELETE-Endpunkten.
- **„Neuer Chat"-Button:** Modernes Design mit Plus-Symbol, dunklem Hintergrund und Hover-Zustand.

### Fehlerbehebungen
- **JavaScript-Syntaxfehler** in `static/app.js` behoben (Klammern, Backticks).
- **Task-Statusmeldung „Der Server wurde neu gestartet"** entfernt – falsche Meldung nach Task-Ausführung.
- **Chat-Titelverlust beim Speichern** in `conversation.py` korrigiert – Titel wird jetzt erhalten.
- **Sidebar-Zentrierung:** Widersprüchliche CSS-Regeln bereinigt; Titel und Datum sind wieder linksbündig.
- **Scroll nach Chatwechsel:** `selectChat()` scrollt zuverlässig ans Ende des Scrollcontainers nach dem Laden der Nachrichten.
- **LLMClient fail-safe:** Kein Crash mehr bei fehlender `.env`-Datei.

### Infrastruktur
- Port 8081 für Agent-Web-Frontend.
- `.gitignore` erweitert (Laufzeitdaten, Backups, Logs).
- Logo und Favicon ins Repository aufgenommen.
