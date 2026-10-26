# Changelog

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
