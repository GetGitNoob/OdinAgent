/* =========================================================
   ODIN // LOCAL AI SYSTEM
   Client
   ========================================================= */

const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const chat = document.getElementById("chat");

const dateElement = document.getElementById("date");
const timeElement = document.getElementById("time");
const gpuTemperature = document.getElementById("gpu-temperature");
const gpuUtilization = document.getElementById("gpu-utilization");
const contextUtilization = document.getElementById("context-utilization");


/* =========================================================
   SESSION
   ========================================================= */

let sessionId = "main";


/* =========================================================
   RECOVERY STATE (iOS Safari: App-Wechsel / Reload)
   ========================================================= */

// Laueft gerade ein Chat-Fetch? Dann darf kein Recovery-Refresh
// parallel laufen und keine neue Aufgabe gestartet werden.
let chatInFlight = false;

// Guard gegen parallele History-Refreshes (visibilitychange + pageshow).
let historyRefreshInProgress = false;


/* =========================================================
   CLOCK
   ========================================================= */

function updateClock() {
    const now = new Date();

    if (dateElement) {
        dateElement.textContent = now
            .toLocaleDateString("de-DE", {
                day: "2-digit",
                month: "short",
                year: "numeric"
            })
            .toUpperCase();
    }

    if (timeElement) {
        timeElement.textContent = now.toLocaleTimeString("de-DE", {
            hour: "2-digit",
            minute: "2-digit"
        });
    }
}

updateClock();
setInterval(updateClock, 1000);


/* =========================================================
   SYSTEM STATUS
   ========================================================= */

async function updateSystemStatus() {
    try {
        const response = await fetch("/api/system", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (gpuTemperature) {
            gpuTemperature.textContent =
                data.gpu_temperature !== null &&
                data.gpu_temperature !== undefined
                    ? `${data.gpu_temperature}°C`
                    : "--°C";
        }

        if (gpuUtilization) {
            gpuUtilization.textContent =
                data.gpu_utilization !== null &&
                data.gpu_utilization !== undefined
                    ? `${data.gpu_utilization}%`
                    : "--%";
        }

        if (contextUtilization) {
            const percent = data.context_percent;
            contextUtilization.textContent =
                data.context_percent !== null &&
                data.context_percent !== undefined
                    ? `${data.context_percent}%`
                    : "--%";
            contextUtilization.classList.remove("context-warning", "context-critical");
            if (Number.isFinite(percent) && percent >= 90) {
                contextUtilization.classList.add("context-critical");
            } else if (Number.isFinite(percent) && percent >= 70) {
                contextUtilization.classList.add("context-warning");
            }
            contextUtilization.title = Number.isFinite(data.context_tokens)
                ? `Letzter Modellaufruf: ${data.context_tokens.toLocaleString("de-DE")} / ${data.context_limit.toLocaleString("de-DE")} Prompt-Tokens`
                : "Noch keine Tokenmessung verfügbar";
        }
    } catch (error) {
        console.error("System status error:", error);

        if (gpuTemperature) {
            gpuTemperature.textContent = "--°C";
        }

        if (gpuUtilization) {
            gpuUtilization.textContent = "--%";
        }
        if (contextUtilization) {
            contextUtilization.textContent = "--%";
            contextUtilization.classList.remove("context-warning", "context-critical");
        }
    }
}

updateSystemStatus();
setInterval(updateSystemStatus, 2000);


/* =========================================================
   HELPERS
   ========================================================= */

function getMessageTime() {
    return new Date().toLocaleTimeString("de-DE", {
        hour: "2-digit",
        minute: "2-digit"
    });
}


function scrollToBottom() {
    requestAnimationFrame(() => {
        // Echter Scroll-Container: <main class="chat-container" id="chat">
        const container = document.getElementById("chat");
        if (container) {
            container.scrollTop = container.scrollHeight;
        } else {
            window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
        }
    });
}


/* =========================================================
   USER MESSAGE
   ========================================================= */

function addUserMessage(text) {
    const message = document.createElement("div");

    message.className = "message user-message";

    message.innerHTML = `
        <div class="avatar user-avatar">
            <div class="user-icon">♙</div>
        </div>

        <div class="message-content">
            <div class="message-header">
                <span class="sender">DU</span>
                <span class="message-time">${getMessageTime()}</span>
            </div>

            <div class="message-box">
                <div class="message-text"></div>
                <button class="copy-btn" title="Kopieren">&#x2398;</button>
            </div>
        </div>
    `;

    message.querySelector(".message-text").textContent = text;

    chat.appendChild(message);
    scrollToBottom();
}


/* =========================================================
   ODIN MESSAGE
   ========================================================= */

function createOdinMessage() {
    const message = document.createElement("div");

    message.className = "message odin-message";

    message.innerHTML = `
        <div class="avatar odin-avatar">
            <div class="avatar-core"></div>
        </div>

        <div class="message-content">
            <div class="message-header">
                <span class="sender">ODIN</span>
                <span class="message-time">${getMessageTime()}</span>
            </div>

            <div class="message-box">
                <div class="message-text"></div>
                <button class="copy-btn" title="Kopieren">&#x2398;</button>
            </div>
        </div>
    `;

    chat.appendChild(message);
    scrollToBottom();

    attachCopyButton(message);
    return message.querySelector(".message-text");
}

/* =========================================================
   COPY BUTTON – ASSISTANT-ANTWORTEN KOPIEREN
   ========================================================= */

function attachCopyButton(messageEl) {
    let btn = messageEl.querySelector(".copy-btn");
    const textEl = messageEl.querySelector(".message-text");
    if (!textEl) return;
    // Fallback: Button noch nicht im DOM vorhanden
    if (!btn) {
        const box = messageEl.querySelector(".message-box");
        if (!box) return;
        btn = document.createElement("button");
        btn.className = "copy-btn";
        btn.title = "Kopieren";
        btn.innerHTML = "&#x2398;";
        box.appendChild(btn);
    }

    btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const text = textEl.textContent;
        if (!text.trim()) return;
        try {
            await navigator.clipboard.writeText(text);
        } catch (_) {
            // Fallback für ältere Browser / unsichere Kontexte
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.style.position = "fixed";
            ta.style.opacity = "0";
            ta.style.left = "-9999px";
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            try { document.execCommand("copy"); } catch(__) {}
            document.body.removeChild(ta);
        }
        btn.innerHTML = "&#10003; Kopiert";
        btn.classList.add("copied");
        setTimeout(() => {
            btn.innerHTML = "&#x2398;";
            btn.classList.remove("copied");
        }, 1500);
    });
}





/* =========================================================
   THINKING
   ========================================================= */

function addThinkingMessage() {
    removeThinkingMessage();

    const message = document.createElement("div");

    message.className = "message odin-message";
    message.id = "thinking-message";

    message.innerHTML = `
        <div class="avatar odin-avatar">
            <div class="avatar-core"></div>
        </div>

        <div class="message-content">
            <div class="message-header">
                <span class="sender">ODIN</span>
                <span class="message-time">${getMessageTime()}</span>
            </div>

            <div class="message-box">
                <div class="message-text">
                    <span class="thinking">
                        Denke
                        <span></span>
                        <span></span>
                        <span></span>
                    </span>
                </div>
                <div class="task-status" id="task-status-line" hidden></div>
            </div>
        </div>
    `;

    chat.appendChild(message);
    scrollToBottom();
}


function removeThinkingMessage() {
    const thinking = document.getElementById("thinking-message");

    if (thinking) {
        thinking.remove();
    }
}

/* =========================================================
   LIVE-ZWISCHENSTAENDE (v0.4.0)
   Rendert Task-Updates aus der Task-JSON als Statuszeile in
   der Thinking-Bubble. Keine eigenen LLM-Aufrufe; reine
   Anzeige realer Ereignisse + clientseitige Laufzeit.
   ========================================================= */

// Formatiert ein Update-Event zu kurzem Anzeigetext.
function formatTaskUpdate(update) {
    const type = update.type || "";
    switch (type) {
        case "llm_start":
            return "Denke nach… (Runde " + (update.round || 1) + ")";
        case "tool_start": {
            let detail = "";
            try {
                const args = update.arguments || {};
                if (args.command) detail = ": " + String(args.command).slice(0, 60);
                else if (args.query) detail = ": " + String(args.query).slice(0, 60);
                else if (args.expression) detail = ": " + String(args.expression).slice(0, 60);
                else if (args.path) detail = ": " + String(args.path).slice(0, 60);
            } catch (_) {}
            return "Tool läuft: " + (update.name || "unbekannt") + detail;
        }
        case "tool_done": {
            const dur = typeof update.duration === "number" ? formatSeconds(update.duration) : "";
            return "Fertig: " + (update.name || "Tool") + (dur ? " (" + dur + ")" : "") +
                   (update.success ? "" : " – Fehler");
        }
        case "llm_done":
            return "Antwort fertiggestellt";
        default:
            return type;
    }
}

// Stabiler Referenzzeitpunkt fuer die Task-Laufzeit (monotone Uhr).
// Wird beim ersten Poll gesetzt und darueber NICHT zurueckgesetzt –
// so laeuft der Timer auch ueber Reloads/Poll-Zyklen durch.
let taskTimerBase = null;   // performance.now()-Wert zum Setzen des Bases
let taskTimerOffsetMs = 0;  // bereits gelaufene Zeit bei Setzen des Bases

// Eigenes Intervall fuer die fluessige Laufzeitanzeige (unabhaengig vom
// 1,5-s-Task-Polling). Handle-Guard verhindert doppelte Intervalle.
let taskTimerHandle = null;

// Bereits verarbeitete Update-Events (Index in data.updates), damit jedes
// Ereignis genau einmal in die Zwischenstandsliste wandert.
let taskUpdatesSeen = 0;

// Formatiert Sekunden mit einer Nachkommastelle im deutschen Format ("12,4 s").
function formatSeconds(seconds) {
    return seconds.toFixed(1).replace(".", ",") + " s";
}

// Rechnet die aktuelle Gesamtlaufzeit aus dem stabilen Anker (ms).
function getTaskElapsedMs() {
    if (taskTimerBase === null) return null;
    return taskTimerOffsetMs + (performance.now() - taskTimerBase);
}

// Einmalig den Zeitanker aus started_at ableiten (naive lokale ISO-Zeit,
// OHNE kuenstliches "Z"-Suffix – das hatte die Anzeige um eine Stunde
// verschoben). Danach bleibt der Anker stabil; nur die monotone
// performance.now()-Uhr laeuft weiter.
function ensureTaskTimerAnchor(startedAt) {
    if (taskTimerBase !== null || !startedAt) return;
    const parsed = Date.parse(startedAt);
    if (isNaN(parsed)) return;
    taskTimerOffsetMs = Math.max(0, Date.now() - parsed);
    taskTimerBase = performance.now();
}

// Startet das 100-ms-Intervall (nur wenn noch keines laeuft).
function startTaskTimer() {
    if (taskTimerHandle !== null) return;
    taskTimerHandle = setInterval(tickTaskTimer, 100);
}

// Stoppt das Intervall (Task-Ende, Abbruch, Chatwechsel).
function stopTaskTimer() {
    if (taskTimerHandle !== null) {
        clearInterval(taskTimerHandle);
        taskTimerHandle = null;
    }
}

// Tickt alle 100 ms: aktualisiert NUR die sichtbare Laufzeit in der
// Statuszeile – keine Serveranfrage, kein renderTaskStatus().
function tickTaskTimer() {
    const line = document.getElementById("task-status-line");
    if (!line || line.hidden) return;
    const totalMs = getTaskElapsedMs();
    if (totalMs === null) return;
    const m = line.querySelector(".task-status-time");
    if (m) m.textContent = "läuft seit " + formatSeconds(totalMs / 1000);
}

// Schreibt neue Update-Events (ab zuletzt gesehener Index) als kleine Liste
// unter die Statuszeile – rein DOM-seitig, max. 5 Eintraege sichtbar.
function renderTaskUpdates(updates) {
    const list = document.getElementById("task-updates-list");
    if (!list) return;

    for (let i = taskUpdatesSeen; i < updates.length; i++) {
        const item = document.createElement("div");
        item.className = "task-update-item";
        item.textContent = formatTaskUpdate(updates[i]);
        list.appendChild(item);
    }
    taskUpdatesSeen = updates.length;

    // Auf die letzten 5 Eintraege begrenzen
    while (list.children.length > 5) {
        list.removeChild(list.firstChild);
    }
    list.hidden = list.children.length === 0;
}

// Ruft den Zeitanker auf, verarbeitet neue Events und startet den Timer.
// Wird nur vom Polling aufgerufen – der 100-ms-Tick ist unabhaengig davon.
function renderTaskStatus(data) {
    const line = document.getElementById("task-status-line");
    if (!line) return;

    ensureTaskTimerAnchor(data.started_at);
    startTaskTimer();

    const updates = data.updates || [];
    renderTaskUpdates(updates);

    const last = updates.length ? updates[updates.length - 1] : null;
    const baseText = last ? formatTaskUpdate(last) : "Aufgabe wird vorbereitet…";

    const totalMs = getTaskElapsedMs();
    const elapsedText = totalMs !== null
        ? " · läuft seit " + formatSeconds(totalMs / 1000)
        : "";

    line.innerHTML = "";
    const label = document.createElement("span");
    label.className = "task-status-label";
    label.textContent = baseText + elapsedText;
    line.appendChild(label);

    const time = document.createElement("span");
    time.className = "task-status-time";
    line.appendChild(time);

    const list = document.createElement("div");
    list.id = "task-updates-list";
    list.className = "task-updates";
    list.hidden = true;
    line.appendChild(list);

    line.hidden = false;
}


/* =========================================================
   SEND MESSAGE
   ========================================================= */

async function sendMessage() {
    if (!input || !form) {
        console.error("Chat UI elements missing.");
        return;
    }

    const messageText = input.value.trim();

    if (!messageText) {
        return;
    }

    addUserMessage(messageText);

    input.value = "";
    input.style.height = "";

    if (sendButton) {
        sendButton.disabled = true;
    }

    input.disabled = true;

    addThinkingMessage();

    chatInFlight = true;

    // Eindeutige request_id fuer Idempotenz (verhindert Doppelstarts)
    const requestId = sessionId + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);

    try {
        // 1) Task starten
        const response = await fetch("/api/tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: messageText,
                session_id: sessionId,
                request_id: requestId
            })
        });

        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }

        const taskData = await response.json();
        const taskId = taskData.task_id;

        // Persistieren: bei Reload/Verbindungsabbruch koennen wir den Task weiterpollen
        try {
            localStorage.setItem("odin_active_task", JSON.stringify({
                task_id: taskId,
                request_id: requestId,
                session_id: sessionId
            }));
        } catch (_) {}

        // 2) Polling bis done/error/interrupted
        const result = await pollTask(taskId);

        removeThinkingMessage();

        if (result.status === "done") {
            const odinEl = createOdinMessage();
            odinEl.textContent = result.result || "(leere Antwort)";
            scrollToBottom();
        } else if (result.status === "error") {
            const errEl = createOdinMessage();
            errEl.textContent = "Fehler: " + (result.error || "Unbekannter Fehler");
        } else if (result.status === "interrupted") {
            const intEl = createOdinMessage();
            intEl.textContent = "Der Server wurde neu gestartet. Die Antwort wurde unterbrochen.";
        }
    } catch (error) {
        console.error("Chat error:", error);
        removeThinkingMessage();
        const errorMessage = createOdinMessage();
        errorMessage.textContent = "Fehler: " + (error.message || "Unbekannter Fehler");
    } finally {
        chatInFlight = false;
        clearActiveTask();

        if (sendButton) {
            sendButton.disabled = false;
        }
        input.disabled = false;
        input.focus();
    }
}

/* =========================================================
   TASK POLLING – ASYNCHRONE ANTWORT ABFRAGEN
   ========================================================= */

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 1800000; // 30 Minuten max. Wartezeit (komplexe Aufgaben)

async function pollTask(taskId) {
    const startTime = Date.now();

    while (Date.now() - startTime < POLL_TIMEOUT_MS) {
        await sleep(POLL_INTERVAL_MS);

        let data;
        try {
            const res = await fetch("/api/tasks/" + encodeURIComponent(taskId), { cache: "no-store" });
            if (!res.ok) {
                // Server evtl. kurz nicht erreichbar – weiter versuchen
                continue;
            }
            data = await res.json();
        } catch (_) {
            // Netzwerkfehler (Safari App-Wechsel) – weiter versuchen
            continue;
        }

        if (!data || !data.status) continue;

        if (data.status === "done") {
            return { status: "done", result: data.result || "", tools: data.tools || [] };
        }
        if (data.status === "error") {
            return { status: "error", error: data.error || "Unbekannter Fehler" };
        }
        if (data.status === "interrupted") {
            return { status: "interrupted" };
        }
        // queued oder running → Statuszeile mit Live-Zwischenstaenden aktualisieren
        if (data.status === "running" || data.status === "queued") {
            renderTaskStatus(data);
        }
    }

    return { status: "error", error: "Zeitüberschreitung: Keine Antwort innerhalb von 30 Minuten erhalten. Die Aufgabe läuft evtl. noch auf dem Server weiter – bitte Seite neu laden oder später erneut prüfen." };
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Speichert die aktive Task-ID in localStorage (uebersteht Reload/App-Wechsel)
function saveActiveTask(taskId, requestId, sid) {
    try {
        localStorage.setItem("odin_active_task", JSON.stringify({
            task_id: taskId,
            request_id: requestId,
            session_id: sid
        }));
    } catch (_) {}
}

function clearActiveTask() {
    try {
        localStorage.removeItem("odin_active_task");
    } catch (_) {}
    // Laufzeit-Timer der abgeschlossenen Task zuruecksetzen
    stopTaskTimer();
    taskTimerBase = null;
    taskTimerOffsetMs = 0;
    taskUpdatesSeen = 0;
}

// Beim Seitenstart: Wenn ein Task laeuft, Status abfragen und Ergebnis anzeigen
async function recoverActiveTask() {
    let stored;
    try {
        stored = JSON.parse(localStorage.getItem("odin_active_task"));
    } catch (_) {
        return;
    }
    if (!stored || !stored.task_id) return;

    // Nur relevant, wenn die Session noch dieselbe ist
    if (stored.session_id !== sessionId) {
        clearActiveTask();
        return;
    }

    try {
        const res = await fetch("/api/tasks/" + encodeURIComponent(stored.task_id), { cache: "no-store" });
        if (!res.ok) { clearActiveTask(); return; }
        const data = await res.json();

        if (data.status === "done") {
            removeThinkingMessage();
            const el = createOdinMessage();
            el.textContent = data.result || "(leere Antwort)";
            scrollToBottom();
        } else if (data.status === "error") {
            removeThinkingMessage();
            const el = createOdinMessage();
            el.textContent = "Fehler: " + (data.error || "Unbekannter Fehler");
        } else if (data.status === "interrupted") {
            removeThinkingMessage();
            const el = createOdinMessage();
            el.textContent = "Der Server wurde neu gestartet. Die Antwort wurde unterbrochen.";
        } else {
            // Noch running/queued → weiter pollen im Hintergrund
            chatInFlight = true;
            if (sendButton) sendButton.disabled = true;
            input.disabled = true;
            addThinkingMessage();
            renderTaskStatus(data);
            const result = await pollTask(stored.task_id);
            chatInFlight = false;
            if (sendButton) sendButton.disabled = false;
            input.disabled = false;
            removeThinkingMessage();
            if (result.status === "done") {
                const el = createOdinMessage();
                el.textContent = result.result || "(leere Antwort)";
            } else if (result.status === "error") {
                const el = createOdinMessage();
                el.textContent = "Fehler: " + (result.error || "Unbekannter Fehler");
            }
            input.focus();
        }
    } catch (e) {
        console.warn("recoverActiveTask:", e);
    } finally {
        clearActiveTask();
    }
}


/* =========================================================
   HISTORY RECOVERY (iOS Safari App-Wechsel / Reload)
   ========================================================= */

// Rendert die serverseitig persistierte Historie einer Session neu.
// Verhindert Duplikate: vorhandene DOM-Nachrichten werden gematcht
// (Rolle + Text), nur fehlende Nachrichten werden angehaengt.
async function restoreHistoryFromServer() {
    if (!sessionId || !chat) {
        return;
    }

    // Nie parallel zu einem laufenden Chat-Fetch refreshen.
    if (chatInFlight || historyRefreshInProgress) {
        return;
    }

    historyRefreshInProgress = true;

    try {
        const response = await fetch(
            "/api/sessions/" + encodeURIComponent(sessionId) + "/messages",
            { cache: "no-store" }
        );

        if (!response.ok) {
            console.warn("History-Refresh fehlgeschlagen: HTTP " + response.status);
            return;
        }

        const data = await response.json();
        const messages = Array.isArray(data.messages) ? data.messages : [];

        removeThinkingMessage();

        // Bestehende DOM-Nachrichten (ohne Begruessung) indexieren.
        const existing = Array.from(chat.querySelectorAll(".message"))
            .filter(el => el.id !== "thinking-message")
            .map(el => ({
                role: el.classList.contains("user-message") ? "user" : "assistant",
                text: (el.querySelector(".message-text") || {}).textContent || ""
            }));

        for (const msg of messages) {
            if (!msg || typeof msg.content !== "string") {
                continue;
            }

            const alreadyShown = existing.some(e =>
                e.role === msg.role && e.text === msg.content
            );

            if (alreadyShown) {
                continue;
            }

            if (msg.role === "user") {
                addUserMessage(msg.content);
            } else if (msg.role === "assistant") {
                const element = createOdinMessage();
                element.textContent = msg.content;
            }

            existing.push({ role: msg.role, text: msg.content });
        }

        scrollToBottom();
    } catch (error) {
        // Netzwerkfehler sind hier nicht fatal: beim naechsten
        // visibilitychange wird erneut versucht.
        console.error("History-Refresh error:", error);
    } finally {
        historyRefreshInProgress = false;
    }
}


// iOS Safari pausiert Tabs im Hintergrund und bricht offene Fetch-Streams ab.
// Wenn die Seite wieder sichtbar wird, holen wir die (serverseitig
// abgeschlossene) Antwort aus der persistierten Historie.
document.addEventListener("visibilitychange", function() {
    if (document.visibilityState === "visible") {
        restoreHistoryFromServer();
    }
});

// BFCache-Rueckkehr (Zurueck-Button): persisted=true bedeutet,
// das Dokument wurde aus dem Cache wiederhergestellt.
window.addEventListener("pageshow", function(event) {
    if (event.persisted) {
        restoreHistoryFromServer();
    }
});

// Beim frischen Laden der Seite (z.B. nach "Loading failed"):
// Historie direkt rekonstruieren, damit laufende/abgeschlossene
// Antworten sichtbar werden.
restoreHistoryFromServer();
recoverActiveTask();



/* =========================================================
   SIDEBAR – CHAT-LISTE & NAVIGATION
   ========================================================= */

const sidebar = document.getElementById("sidebar");
const chatListEl = document.getElementById("chat-list");
const newChatBtn = document.getElementById("new-chat-btn");
const sidebarToggle = document.getElementById("sidebar-toggle");

// Lädt die Chatliste aus dem Backend und rendert sie in der Sidebar.
async function loadChatList() {
    if (!chatListEl) return;
    try {
        const res = await fetch("/api/chats", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        const chats = Array.isArray(data.chats) ? data.chats : [];

        chatListEl.innerHTML = "";
        for (const c of chats) {
            const item = document.createElement("div");
            item.className = "sidebar-chat-item" + (c.id === sessionId ? " active" : "");
            item.dataset.sessionId = c.id;

            // Info-Wrapper (Titel + Datum linksbündig)
            const info = document.createElement("div");
            info.className = "sidebar-chat-info";

            const title = document.createElement("span");
            title.className = "sidebar-chat-title";
            title.textContent = c.title || "Neuer Chat";

            const date = document.createElement("span");
            date.className = "sidebar-chat-date";
            date.textContent = c.updated ? new Date(c.updated).toLocaleDateString("de-DE", { day: "2-digit", month: "short" }) : "";

            info.appendChild(title);
            info.appendChild(date);

            // Aktions-Buttons (Umbenennen + Löschen)
            const actions = document.createElement("div");
            actions.className = "sidebar-chat-actions";

            const renameBtn = document.createElement("button");
            renameBtn.className = "chat-action-btn rename-btn";
            renameBtn.title = "Umbenennen";
            renameBtn.textContent = "✎";
            renameBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                showRenamePrompt(c.id, c.title || "Neuer Chat");
            });

            const deleteBtn = document.createElement("button");
            deleteBtn.className = "chat-action-btn delete-btn";
            deleteBtn.title = "Löschen";
            deleteBtn.textContent = "✕";
            deleteBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                confirmDeleteChat(c.id, c.title || "Neuer Chat");
            });

            actions.appendChild(renameBtn);
            actions.appendChild(deleteBtn);

            item.appendChild(info);
            item.appendChild(actions);
            item.addEventListener("click", () => selectChat(c.id));
            chatListEl.appendChild(item);
        }
    } catch (e) {
        console.warn("loadChatList:", e);
    }
}

// Umbenennen: Prompt → PUT /api/chats/{id}/rename → Sidebar aktualisieren
async function showRenamePrompt(chatId, currentTitle) {
    const newTitle = prompt("Chat umbenennen:", currentTitle);
    if (!newTitle || newTitle.trim() === "") return;
    try {
        const res = await fetch("/api/chats/" + encodeURIComponent(chatId) + "/rename", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: newTitle.trim() })
        });
        if (res.ok) {
            loadChatList();
        } else {
            alert("Umbenennen fehlgeschlagen: HTTP " + res.status);
        }
    } catch (e) {
        alert("Umbenennen fehlgeschlagen: " + e.message);
    }
}

// Löschen: Bestätigung → DELETE /api/chats/{id} → Sidebar aktualisieren
async function confirmDeleteChat(chatId, title) {
    if (!confirm("Chat \"" + title + "\" wirklich löschen?\nDie Nachrichtenhistorie wird dauerhaft entfernt.")) return;
    try {
        const res = await fetch("/api/chats/" + encodeURIComponent(chatId), { method: "DELETE" });
        if (res.ok) {
            // Wenn der aktive Chat gelöscht wurde → neuen starten
            if (chatId === sessionId) {
                createNewChat();
            }
            loadChatList();
        } else {
            alert("Löschen fehlgeschlagen: HTTP " + res.status);
        }
    } catch (e) {
        alert("Löschen fehlgeschlagen: " + e.message);
    }
}

// Wechselt zu einem bestehenden Chat: lädt Historie, markiert aktiv.
async function selectChat(chatId) {
    if (chatInFlight) return; // Kein Wechsel während laufender Antwort
    sessionId = chatId;
    chat.innerHTML = "";
    await restoreHistoryFromServer();
    // Sicherstellen, dass alle Nachrichten gerendert sind, dann scrollen
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            scrollToBottom();
        });
    });
    loadChatList(); // Active-Markierung aktualisieren
    closeSidebarMobile();
}

// Erzeugt eine neue Session mit eindeutiger ID.
function createNewChat() {
    if (chatInFlight) return;
    sessionId = "chat-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 7);
    chat.innerHTML = "";
    loadChatList();
    closeSidebarMobile();
    if (input) input.focus();
}

// Mobile: Sidebar schließen
function closeSidebarMobile() {
    if (sidebar) sidebar.classList.remove("open");
}

// Event-Listener
if (newChatBtn) {
    newChatBtn.addEventListener("click", createNewChat);
}
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
        if (!sidebar) return;
        sidebar.classList.toggle("open");
        if (sidebarBackdrop) sidebarBackdrop.classList.toggle("visible", sidebar.classList.contains("open"));
    });
}
// Backdrop-Klick schließt Sidebar
if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener("click", () => {
        if (sidebar) sidebar.classList.remove("open");
        sidebarBackdrop.classList.remove("visible");
    });
}
// Auf Mobilgeräten: Klick außerhalb schließt Sidebar
document.addEventListener("click", (e) => {
    if (sidebar && sidebar.classList.contains("open")
        && !sidebar.contains(e.target)
        && e.target !== sidebarToggle
        && e.target !== sidebarBackdrop) {
        sidebar.classList.remove("open");
        if (sidebarBackdrop) sidebarBackdrop.classList.remove("visible");
    }
});

// Beim Start: Chatliste laden
loadChatList();


/* =========================================================
   FORM SUBMIT
   ========================================================= */

if (form) {
    form.addEventListener("submit", function(event) {
        event.preventDefault();
        sendMessage();
    });
}


/* =========================================================
   ENTER KEY
   ========================================================= */

if (input) {
    input.addEventListener("keydown", function(event) {
        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {
            event.preventDefault();
            sendMessage();
        }
    });

    input.addEventListener("input", function() {
        input.style.height = "auto";
        input.style.height =
            Math.min(input.scrollHeight, 180) + "px";
    });
}


/* =========================================================
   INITIAL FOCUS
   ========================================================= */

if (input) {
    input.focus();
}

console.log("ODIN client initialized.");

