// Configure marked to use highlight.js for code blocks
marked.setOptions({
    highlight: (code, lang) => {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    }
});

const chatContainer = document.getElementById('chatContainer');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');

// ── Socket.IO ───────────────────────────────────────────────
const socket = io();

socket.on('connect', () => {
    console.log('✅ WebSocket connected:', socket.id);
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    if (dot) dot.className = 'status-dot connected';
    if (text) text.textContent = 'Connected';
});
socket.on('disconnect', () => {
    console.warn('⚠️ WebSocket disconnected');
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    if (dot) dot.className = 'status-dot disconnected';
    if (text) text.textContent = 'Disconnected';
});

// Track the assistant bubble being built during a stream
let streamingBubble = null;
let streamingText = '';
let thinkingBubble = null;
let streamDone = false;

// ── Word-level render buffer ─────────────────────────────────
// Incoming chunks are split into words and pushed into wordBuffer.
// A fixed-interval ticker drains one word at a time at a constant
// pace — completely decoupled from how fast/slow chunks arrive.
// This gives smooth, steady streaming regardless of network timing.
const wordBuffer = [];
const RENDER_INTERVAL_MS = 38;   // one word every ~38ms ≈ natural reading pace
let renderTicker = null;

function startTicker() {
    if (renderTicker) return;
    renderTicker = setInterval(() => {
        if (wordBuffer.length === 0) {
            if (streamDone) stopTicker();
            return;
        }
        const word = wordBuffer.shift();
        removeThinking();
        if (!streamingBubble) {
            streamingBubble = addMessage('', 'assistant');
            streamingText = '';
        }
        streamingText += word;
        // Ensure inline numbered list items are on their own lines before parsing
        const mdText = streamingText.replace(/ (\d+)\. /g, '\n\n$1. ');
        streamingBubble.querySelector('.message-content').innerHTML = marked.parse(mdText);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }, RENDER_INTERVAL_MS);
}

function stopTicker() {
    if (renderTicker) { clearInterval(renderTicker); renderTicker = null; }
    // Apply syntax highlighting to any code blocks in the completed bubble
    if (streamingBubble) {
        streamingBubble.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
    }
    streamDone = false;
    streamingBubble = null;
    streamingText = '';
    sendBtn.disabled = false;
    userInput.focus();
}

function resetBuffer() {
    wordBuffer.length = 0;
    if (renderTicker) { clearInterval(renderTicker); renderTicker = null; }
    streamDone = false;
    streamingBubble = null;
    streamingText = '';
}
// ─────────────────────────────────────────────────────────────

function showThinking() {
    thinkingBubble = document.createElement('div');
    thinkingBubble.className = 'message assistant typing-indicator';
    thinkingBubble.innerHTML = '<div class="message-content"><div class="dot"></div><div class="dot"></div><div class="dot"></div><span class="typing-text"></span></div>';
    chatContainer.appendChild(thinkingBubble);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function removeThinking() {
    if (thinkingBubble) {
        thinkingBubble.remove();
        thinkingBubble = null;
    }
}

socket.on('chat_chunk', ({ chunk }) => {
    // Split chunk into words and push each into the render buffer
    // A trailing space preserves word separation between chunks
    const words = chunk.split(/(?<=\s)|(?=\s)/).filter(w => w.length > 0);
    words.forEach(w => wordBuffer.push(w));
    startTicker();
});

socket.on('chat_status', ({ agent }) => {
    // Update thinking bubble text with which sub-agent is processing
    if (thinkingBubble) {
        const textEl = thinkingBubble.querySelector('.typing-text');
        if (textEl) textEl.textContent = `${agent} is working...`;
    }
});

socket.on('chat_done', () => {
    // Always clear the thinking bubble — it may still be showing if no chunks arrived
    removeThinking();
    // Signal the ticker to stop once the buffer is empty
    streamDone = true;
    if (wordBuffer.length === 0 && !renderTicker) stopTicker();
});

socket.on('chat_error', ({ error }) => {
    resetBuffer();
    removeThinking();
    addMessage(error || 'An error occurred', 'error');
    sendBtn.disabled = false;
    userInput.focus();
});

// ── UI helpers ────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', function() {
    // Do not persist chat history between app restarts/page reloads.
    addMessage('👋 Hello! I\'m your Google ADK agent. How can I help you today?', 'assistant');
});

userInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto-resize textarea as user types
userInput.addEventListener('input', function() {
    this.style.height = 'auto';
    const newHeight = Math.min(this.scrollHeight, 120);
    this.style.height = newHeight + 'px';
    // Only show scrollbar when content exceeds the max height
    this.classList.toggle('scrollable', this.scrollHeight > 120);
});

function addMessage(content, type = 'assistant', existingTime = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    if (type === 'assistant') {
        contentDiv.innerHTML = marked.parse(content);
        contentDiv.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
    } else {
        contentDiv.textContent = content;
    }
    messageDiv.appendChild(contentDiv);

    // Meta row: timestamp + copy button (assistant only)
    const metaDiv = document.createElement('div');
    metaDiv.className = 'message-meta';

    const timeSpan = document.createElement('span');
    timeSpan.className = 'message-time';
    timeSpan.textContent = existingTime || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    metaDiv.appendChild(timeSpan);

    if (type === 'assistant') {
        const copyBtn = document.createElement('button');
        copyBtn.className = 'copy-btn';
        copyBtn.textContent = 'Copy';
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(contentDiv.innerText).then(() => {
                copyBtn.textContent = '✓ Copied';
                setTimeout(() => copyBtn.textContent = 'Copy', 2000);
            });
        });
        metaDiv.appendChild(copyBtn);
    }
    messageDiv.appendChild(metaDiv);

    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return messageDiv;
}

// ── Send via WebSocket ───────────────────────────────────
function clearChat() {
    chatContainer.innerHTML = '';
    addMessage('👋 Hello! I\'m your Google ADK agent. How can I help you today?', 'assistant');
}

function sendMessage() {
    const message = userInput.value.trim();
    if (!message || sendBtn.disabled) return;

    addMessage(message, 'user');
    userInput.value = '';
    userInput.style.height = 'auto';
    userInput.classList.remove('scrollable');
    sendBtn.disabled = true;
    showThinking();

    // Server streams back via chat_chunk → chat_done (or chat_error)
    socket.emit('chat_message', { message });
}
