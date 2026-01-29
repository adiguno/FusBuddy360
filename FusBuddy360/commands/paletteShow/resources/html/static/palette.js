function byId(id) {
    return document.getElementById(id);
}

function nowTime() {
    const d = new Date();
    const pad = (n) => `${n}`.padStart(2, "0");
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function setStatus(text, isError = false) {
    const el = byId("status");
    el.textContent = text;
    el.classList.toggle("error", isError);
}

function parseMarkdownToHTML(text) {
    // Split into lines for processing
    const lines = text.split('\n');
    const output = [];
    let inParagraph = false;
    let stepCounter = 0;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        const nextLine = i < lines.length - 1 ? lines[i + 1].trim() : '';
        
        // Headings
        if (line.startsWith('### ')) {
            if (inParagraph) { output.push('</p>'); inParagraph = false; }
            output.push('<h3>' + escapeHTML(parseInlineMarkdown(line.substring(4))) + '</h3>');
            continue;
        }
        if (line.startsWith('## ')) {
            if (inParagraph) { output.push('</p>'); inParagraph = false; }
            output.push('<h2>' + escapeHTML(parseInlineMarkdown(line.substring(3))) + '</h2>');
            continue;
        }
        if (line.startsWith('# ')) {
            if (inParagraph) { output.push('</p>'); inParagraph = false; }
            output.push('<h1>' + escapeHTML(parseInlineMarkdown(line.substring(2))) + '</h1>');
            continue;
        }
        
        // Numbered list items (1. or 1))
        const numberedMatch = line.match(/^(\d+)[.)]\s+(.+)$/);
        if (numberedMatch) {
            if (inParagraph) { output.push('</p>'); inParagraph = false; }
            const stepText = numberedMatch[2];
            const id = `step-${Date.now()}-${stepCounter++}`;
            output.push(`<label class="step-item"><input type="checkbox" class="step-checkbox" id="${id}"><span class="step-text">${parseInlineMarkdown(stepText)}</span></label>`);
            continue;
        }
        
        // Empty line - end paragraph
        if (line === '') {
            if (inParagraph) {
                output.push('</p>');
                inParagraph = false;
            }
            continue;
        }
        
        // Regular paragraph text
        if (!inParagraph) {
            output.push('<p>');
            inParagraph = true;
        } else {
            output.push('<br>');
        }
        output.push(parseInlineMarkdown(line));
    }
    
    if (inParagraph) {
        output.push('</p>');
    }
    
    return output.join('');
}

function escapeHTML(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function parseInlineMarkdown(text) {
    let html = escapeHTML(text);
    
    // Bold (**text** or __text__) - process bold first to avoid conflicts
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    
    // Italic (*text* or _text_) - match single asterisks/underscores
    // Use a simple pattern that avoids matching ** or __
    html = html.replace(/\b\*([^*\n]+?)\*\b/g, '<em>$1</em>');
    html = html.replace(/\b_([^_\n]+?)_\b/g, '<em>$1</em>');
    
    return html;
}

function appendMessage(role, text) {
    const container = byId("messages");
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    
    if (role === "assistant") {
        // Parse markdown for assistant messages
        wrap.innerHTML = parseMarkdownToHTML(text);
    } else {
        // Plain text for user messages
        wrap.textContent = text;
    }

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${role === "user" ? "You" : "FusBuddy360"} • ${nowTime()}`;

    const outer = document.createElement("div");
    outer.appendChild(wrap);
    outer.appendChild(meta);

    container.appendChild(outer);
    container.scrollTop = container.scrollHeight;
}

function updateContext(jsonString) {
    const el = byId("context");
    let obj = null;
    try {
        obj = JSON.parse(jsonString);
        el.textContent = JSON.stringify(obj, null, 2);
    } catch (e) {
        el.textContent = jsonString;
    }

    // Update screenshot preview if available
    const img = byId("screenshotPreview");
    if (!img) return;

    try {
        const screenshot = obj && obj.screenshot ? obj.screenshot : null;
        if (screenshot && screenshot.base64) {
            img.src = `data:image/png;base64,${screenshot.base64}`;
            img.style.display = "block";
        } else {
            img.src = "";
            img.style.display = "none";
        }
    } catch (e) {
        img.src = "";
        img.style.display = "none";
    }
}

async function sendUserQuery() {
    const input = byId("chatInput");
    const sendBtn = byId("sendBtn");
    const text = (input.value || "").trim();
    if (!text) return;

    appendMessage("user", text);
    input.value = "";
    input.focus();

    sendBtn.disabled = true;
    setStatus("Sending to Fusion…");

    try {
        const payload = { text };
        // Send to Fusion. The return value is a Promise (html_args.returnData).
        const result = await adsk.fusionSendData("userQuery", JSON.stringify(payload));
        setStatus(`Fusion received. (${result})`);
    } catch (e) {
        console.log(e);
        setStatus("Failed to send message to Fusion. See console.", true);
    } finally {
        sendBtn.disabled = false;
    }
}

async function saveApiKey(provider) {
    const input = byId(provider === "openai" ? "openaiKeyInput" : "geminiKeyInput");
    const key = (input?.value || "").trim();
    if (!key) {
        setStatus(`Enter a ${provider === "openai" ? "OpenAI" : "Gemini"} API key before saving.`, true);
        return;
    }

    setStatus(`Saving ${provider === "openai" ? "OpenAI" : "Gemini"} API key…`);
    try {
        const payload = { apiKey: key, provider: provider };
        const result = await adsk.fusionSendData("saveApiKey", JSON.stringify(payload));
        setStatus(result || "API key saved.");
        if (input) input.value = ""; // Clear input after saving
    } catch (e) {
        console.log(e);
        setStatus("Failed to save API key. See console.", true);
    }
}

window.fusionJavaScriptHandler = {
    handle: function (action, data) {
        try {
            if (action === "assistantMessage") {
                const msg = JSON.parse(data);
                appendMessage("assistant", msg.text ?? `${msg}`);
                setStatus("Ready.");
            } else if (action === "contextUpdate") {
                updateContext(data);
            } else if (action === "debugger") {
                debugger;
            } else {
                return `Unexpected command type: ${action}`;
            }
        } catch (e) {
            console.log(e);
            console.log(`Exception caught with command: ${action}, data: ${data}`);
            setStatus(`Error handling message from Fusion: ${action}`, true);
        }
        return "OK";
    },
};

// Wire up UI once DOM is ready.
window.addEventListener("DOMContentLoaded", () => {
    byId("sendBtn").addEventListener("click", sendUserQuery);
    byId("chatInput").addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendUserQuery();
        }
    });

    const saveOpenAIBtn = byId("saveOpenAIKeyBtn");
    if (saveOpenAIBtn) {
        saveOpenAIBtn.addEventListener("click", () => saveApiKey("openai"));
    }

    const saveGeminiBtn = byId("saveGeminiKeyBtn");
    if (saveGeminiBtn) {
        saveGeminiBtn.addEventListener("click", () => saveApiKey("gemini"));
    }

    appendMessage("assistant", "Hi — I’m FusBuddy360. Ask me how to do something in Fusion 360.");
    setStatus("Ready.");
});
