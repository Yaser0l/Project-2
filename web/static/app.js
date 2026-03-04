const chatContainer = document.getElementById('chatContainer');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');

// ── Socket.IO ───────────────────────────────────────────────
const socket = io();

socket.on('connect', () => console.log('✅ WebSocket connected:', socket.id));
socket.on('disconnect', () => console.warn('⚠️ WebSocket disconnected'));

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
        streamingBubble.querySelector('.message-content').innerHTML = marked.parse(streamingText);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }, RENDER_INTERVAL_MS);
}

function stopTicker() {
    if (renderTicker) { clearInterval(renderTicker); renderTicker = null; }
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
    thinkingBubble.innerHTML = '<div class="message-content"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
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

socket.on('chat_done', () => {
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
    addMessage('👋 Hello! I\'m your Google ADK agent. How can I help you today?', 'assistant');
});

userInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

function addMessage(content, type = 'assistant') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    if (type === 'assistant') {
        contentDiv.innerHTML = marked.parse(content);
    } else {
        contentDiv.textContent = content;
    }
    messageDiv.appendChild(contentDiv);
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return messageDiv;
}

// ── Send via WebSocket ───────────────────────────────────
function sendMessage() {
    const message = userInput.value.trim();
    if (!message || sendBtn.disabled) return;

    addMessage(message, 'user');
    userInput.value = '';
    sendBtn.disabled = true;
    showThinking();

    // Server streams back via chat_chunk → chat_done (or chat_error)
    socket.emit('chat_message', { message });
}
