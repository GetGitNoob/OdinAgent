/* =========================================================
   ODIN // LOCAL AI SYSTEM
   Client
   ========================================================= */


/* =========================================================
   ELEMENTS
   ========================================================= */

const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const chat = document.getElementById("chat");

const dateElement = document.getElementById("date");
const timeElement = document.getElementById("time");


/* =========================================================
   SESSION
   ========================================================= */

let sessionId = localStorage.getItem("odin-session-id");

if (!sessionId) {

    sessionId =
        "odin-" +
        Date.now().toString(36) +
        "-" +
        Math.random().toString(36).substring(2, 10);

    localStorage.setItem(
        "odin-session-id",
        sessionId
    );
}

/* =========================================================
   CLOCK
   ========================================================= */

function updateClock() {

    const now = new Date();

    const date = now.toLocaleDateString("de-DE", {
        day: "2-digit",
        month: "short",
        year: "numeric"
    }).toUpperCase();

    const time = now.toLocaleTimeString("de-DE", {
        hour: "2-digit",
        minute: "2-digit"
    });

    dateElement.textContent = date;
    timeElement.textContent = time;
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

        const temperature =
            document.getElementById("gpu-temperature");

        const utilization =
            document.getElementById("gpu-utilization");


        if (temperature) {

            temperature.textContent =
                data.gpu_temperature !== null
                    ? `${data.gpu_temperature}°C`
                    : "--°C";
        }


        if (utilization) {

            utilization.textContent =
                data.gpu_utilization !== null
                    ? `${data.gpu_utilization}%`
                    : "--%";
        }

    } catch (error) {

        console.error(
            "System status error:",
            error
        );
    }
}


updateSystemStatus();


setInterval(
    updateSystemStatus,
    2000
);


/* =========================================================
   MESSAGE TIME
   ========================================================= */

function getMessageTime() {

    return new Date().toLocaleTimeString("de-DE", {
        hour: "2-digit",
        minute: "2-digit"
    });
}


/* =========================================================
   ADD USER MESSAGE
   ========================================================= */

function addUserMessage(text) {

    const message =
        document.createElement("div");

    message.className =
        "message user-message";


    message.innerHTML = `
        <div class="avatar user-avatar">
            <div class="user-icon">♙</div>
        </div>

        <div class="message-content">

            <div class="message-header">

                <span class="sender">
                    DU
                </span>

                <span class="message-time">
                    ${getMessageTime()}
                </span>

            </div>

            <div class="message-box">

                <div class="message-text"></div>

            </div>

        </div>
    `;


    message.querySelector(
        ".message-text"
    ).textContent = text;


    chat.appendChild(message);

    scrollToBottom();
}


/* =========================================================
   CREATE ODIN MESSAGE
   ========================================================= */

function createOdinMessage() {

    const message =
        document.createElement("div");

    message.className =
        "message odin-message";


    message.innerHTML = `
        <div class="avatar odin-avatar">
            <div class="avatar-core"></div>
        </div>

        <div class="message-content">

            <div class="message-header">

                <span class="sender">
                    ODIN
                </span>

                <span class="message-time">
                    ${getMessageTime()}
                </span>

            </div>

            <div class="message-box">

                <div class="message-text"></div>

            </div>

        </div>
    `;


    chat.appendChild(message);

    scrollToBottom();


    return message.querySelector(
        ".message-text"
    );
}


/* =========================================================
   THINKING MESSAGE
   ========================================================= */

function addThinkingMessage() {

    const message =
        document.createElement("div");

    message.className =
        "message odin-message";

    message.id =
        "thinking-message";


    message.innerHTML = `
        <div class="avatar odin-avatar">
            <div class="avatar-core"></div>
        </div>

        <div class="message-content">

            <div class="message-header">

                <span class="sender">
                    ODIN
                </span>

                <span class="message-time">
                    ${getMessageTime()}
                </span>

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

            </div>

        </div>
    `;


    chat.appendChild(message);

    scrollToBottom();
}


/* =========================================================
   REMOVE THINKING MESSAGE
   ========================================================= */

function removeThinkingMessage() {

    const thinking =
        document.getElementById(
            "thinking-message"
        );

    if (thinking) {
        thinking.remove();
    }
}


/* =========================================================
   SCROLL
   ========================================================= */

function scrollToBottom() {

    chat.scrollTo({
        top: chat.scrollHeight,
        behavior: "smooth"
    });
}


/* =========================================================
   STREAM CHAT RESPONSE
   ========================================================= */

async function streamMessage(message) {

    const response =
        await fetch("/api/chat", {

            method: "POST",

            headers: {
                "Content-Type":
                    "application/json"
            },

            body: JSON.stringify({

                message: message,

                session_id: sessionId

            })
        });


    if (!response.ok) {

        throw new Error(
            `HTTP ${response.status}`
        );
    }


    if (!response.body) {

        throw new Error(
            "Streaming wird vom Browser nicht unterstützt."
        );
    }


    removeThinkingMessage();


    const textElement =
        createOdinMessage();


    const reader =
        response.body.getReader();


    const decoder =
        new TextDecoder("utf-8");


    let buffer = "";


    while (true) {

        const {
            value,
            done
        } = await reader.read();


        if (done) {
            break;
        }


        buffer += decoder.decode(
            value,
            {
                stream: true
            }
        );


        const events =
            buffer.split("\n\n");


        buffer =
            events.pop();


        for (const event of events) {

            const line =
                event
                    .split("\n")
                    .find(line =>
                        line.startsWith("data:")
                    );


            if (!line) {
                continue;
            }


            const data =
                line
                    .substring(5)
                    .trim();


            if (data === "[DONE]") {
                continue;
            }


            try {

                const parsed =
                    JSON.parse(data);


                if (parsed.error) {

                    throw new Error(
                        parsed.error
                    );
                }


                if (parsed.content) {

                    textElement.textContent +=
                        parsed.content;

                    scrollToBottom();
                }

                if (parsed.type === "tool") {

                    addToolCard(
                        parsed.tool,
                        parsed.arguments
                    );
                }

            } catch (error) {

                console.error(
                    "Stream parsing error:",
                    error
                );
            }
        }
    }


    decoder.decode();

    scrollToBottom();
}


/* =========================================================
   TOOL ACTIVITY CARD
   ========================================================= */

function addToolCard(name, args) {

    const message =
        document.createElement("div");

    message.className =
        "message tool-message";

    let argPreview = "";
    try {
        argPreview = JSON.stringify(args || {});
    } catch (e) {
        argPreview = "";
    }

    message.innerHTML = \`
        <div class="tool-icon" aria-hidden="true">&#9881;</div>
        <div class="tool-info">
            <span class="tool-name">\${name}</span>
            <span class="tool-args">\${argPreview}</span>
        </div>
    \`;

    const thinking =
        document.getElementById("thinking-message");

    const lastOdin =
        Array.from(chat.querySelectorAll(".message.odin-message"))
            .pop();

    const refNode =
        thinking || lastOdin;

    if (refNode) {
        chat.insertBefore(message, refNode);
    } else {
        chat.appendChild(message);
    }

    scrollToBottom();
}

/* =========================================================
   SEND MESSAGE
   ========================================================= */

async function sendMessage() {

    const message =
        input.value.trim();


    if (!message) {
        return;
    }


    input.disabled = true;
    sendButton.disabled = true;


    addUserMessage(message);

    input.value = "";


    addThinkingMessage();


    try {

        await streamMessage(message);

    } catch (error) {

        console.error(
            "Chat error:",
            error
        );


        removeThinkingMessage();


        addOdinMessageError(
            "Fehler: Der Odin-Agent konnte nicht erreicht werden."
        );
    }


    input.disabled = false;
    sendButton.disabled = false;

    input.focus();
}


/* =========================================================
   ERROR MESSAGE
   ========================================================= */

function addOdinMessageError(text) {

    const textElement =
        createOdinMessage();

    textElement.textContent =
        text;
}


/* =========================================================
   FORM SUBMIT
   ========================================================= */

form.addEventListener(
    "submit",
    function (event) {

        event.preventDefault();

        sendMessage();
    }
);


/* =========================================================
   ENTER KEY
   ========================================================= */

input.addEventListener(
    "keydown",
    function (event) {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            sendMessage();
        }
    }
);


/* =========================================================
   INITIAL FOCUS
   ========================================================= */

input.focus();