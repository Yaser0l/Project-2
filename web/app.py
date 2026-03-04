"""
Google ADK Agent API Server
A Flask-based REST API for interacting with Google ADK agents.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import from GoogleADK
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit as ws_emit
from GoogleADK.agent import guardrail, root_agent
import logging
import asyncio
from google.adk.runners import InMemoryRunner
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai.types import Content, Part

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='static')

# WebSocket server — threading mode lets each handler run its own asyncio loop
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Global variables for agent runner and session
runner = None
session = None

async def initialize_agent():
    """Initialize the ADK runner and session"""
    global runner, session
    logger.info("🚀 Initializing Google ADK agents...")
    runner = InMemoryRunner(agent=root_agent, app_name="BookAgent")
    session = await runner.session_service.create_session(
        app_name="BookAgent", 
        user_id="user1"
    )
    logger.info("✅ Agents initialized successfully")

async def process_message(user_input: str) -> str:
    """
    Process a user message through the Google ADK agent (non-streaming, used by REST endpoint).
    """
    global runner, session
    message = Content(role="user", parts=[Part(text=user_input)])
    final_response = None
    try:
        async for event in runner.run_async(
            user_id="user1",
            session_id=session.id,
            new_message=message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text and part.text.strip():
                        text = part.text.strip()
                        if not text.startswith("For context:") and not text.startswith("["):
                            final_response = text
                        break
        return final_response if final_response else "I couldn't generate a response. Please try again."
    except Exception as e:
        if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
            return "⚠️ Rate limit exceeded. Please wait a moment before trying again."
        else:
            raise e


async def stream_message(sid: str, user_input: str) -> None:
    """
    Stream a response to the WebSocket client.

    ADK's multi-agent pipeline aggregates sub-agent results before the Manager
    emits them, so even with StreamingMode.SSE the Manager's relay response
    arrives as a single complete event (one token) rather than word-by-word.

    Strategy:
    - If ADK yields genuine partial tokens (is_partial=True) we emit each one
      immediately — real LLM streaming.
    - If the text arrives as a single complete block (relay case), we break it
      into small word-groups and emit them with tiny async delays — real multiple
      WebSocket messages that the client receives and renders one by one.
    """
    global runner, session

    run_config = RunConfig(streaming_mode=StreamingMode.SSE)
    message = Content(role="user", parts=[Part(text=user_input)])

    partial_streamed = False

    async def emit_words(text: str, words_per_chunk: int = 3, delay: float = 0.04):
        """Break text into small word-groups, emitting each as a separate WS message."""
        words = text.split(" ")
        for i in range(0, len(words), words_per_chunk):
            chunk = " ".join(words[i:i + words_per_chunk])
            if i + words_per_chunk < len(words):
                chunk += " "          # restore the space between groups
            socketio.emit("chat_chunk", {"chunk": chunk}, to=sid)
            await asyncio.sleep(delay)

    try:
        async for event in runner.run_async(
            user_id="user1",
            session_id=session.id,
            new_message=message,
            run_config=run_config,
        ):
            if not event.content or not event.content.parts:
                continue

            is_partial = getattr(event, "partial", False)
            is_manager = getattr(event, "author", None) == "Manager"

            # Only handle Manager events — sub-agent events would duplicate
            # whatever the Manager relays to the user.
            if not is_manager:
                continue

            for part in event.content.parts:
                if not (hasattr(part, "text") and part.text and part.text.strip()):
                    continue
                text = part.text.strip()
                if text.startswith("For context:") or text.startswith("["):
                    continue

                if is_partial:
                    # Genuine LLM partial token — emit immediately, client buffers
                    logger.info(f"📡 [WS] partial → {sid}: {text[:60]}...")
                    socketio.emit("chat_chunk", {"chunk": text}, to=sid)
                    partial_streamed = True
                elif not partial_streamed:
                    # Single-block relay: stream word-by-word over WebSocket
                    logger.info(f"📡 [WS] word-streaming → {sid}: {text[:60]}...")
                    await emit_words(text)
                # else: final event after partials — already fully sent, skip
                break

        socketio.emit("chat_done", {}, to=sid)
        logger.info(f"✅ [WS] stream complete for {sid}")

    except Exception as e:
        if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
            socketio.emit("chat_error", {
                "error": "⚠️ Rate limit exceeded. Please wait a moment before trying again."
            }, to=sid)
        else:
            logger.error(f"❌ [WS] error for {sid}: {e}")
            socketio.emit("chat_error", {"error": f"Server error: {str(e)}"}, to=sid)


# ── WebSocket events ──────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    logger.info(f"🔌 [WS] Client connected: {request.sid}")
    ws_emit("connected", {"status": "connected"})


@socketio.on("disconnect")
def on_disconnect():
    logger.info(f"🔌 [WS] Client disconnected: {request.sid}")


@socketio.on("chat_message")
def handle_ws_chat(data):
    """
    WebSocket event: 'chat_message'
    Payload:  { "message": "<user text>" }

    Streams back:
      'chat_chunk' { chunk: "..." }  — one event per streamed partial response
      'chat_done'  {}                — end of stream
      'chat_error' { error: "..." } — on failure
    """
    sid = request.sid
    user_message = (data or {}).get("message", "").strip()

    if not user_message:
        socketio.emit("chat_error", {"error": "No message provided"}, to=sid)
        return

    logger.info(f"📨 [WS] from {sid}: {user_message[:100]}")

    validation = guardrail(user_message)
    if not validation["allowed"]:
        logger.warning(f"🚫 [WS] blocked for {sid}: {validation['reason']}")
        socketio.emit("chat_error", {"error": validation["reason"]}, to=sid)
        return

    sanitized = validation["sanitized_input"]
    logger.info(f"🤖 [WS] streaming SSE response to {sid}...")

    # flask-socketio threading mode gives each handler its own thread,
    # so creating a fresh event loop here is safe.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(stream_message(sid, sanitized))
    finally:
        loop.close()


# ── HTTP routes ───────────────────────────────────────────────────────────────

# Routes
@app.route('/')
def home():
    """Serve the main HTML page"""
    return send_from_directory('static', 'index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    API endpoint for chat messages.
    
    Request body:
        {
            "message": "user message here"
        }
        
    Response:
        {
            "response": "agent response here",
            "status": "success"
        }
        
    Error response:
        {
            "error": "error message here"
        }
    """
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400
        
        user_message = data['message']
        logger.info(f"📨 Received message: {user_message[:100]}...")
        
        # Apply guardrail validation
        validation = guardrail(user_message)
        
        if not validation['allowed']:
            logger.warning(f"🚫 Input blocked: {validation['reason']}")
            return jsonify({'error': validation['reason']}), 400
        
        # Process with agent
        sanitized_input = validation['sanitized_input']
        logger.info("🤖 Processing with agent...")
        
        # Run agent asynchronously
        response_text = asyncio.run(process_message(sanitized_input))
        
        logger.info(f"✅ Response generated: {response_text[:100]}...")
        
        return jsonify({
            'response': response_text,
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"❌ Error processing request: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """
    Health check endpoint.
    
    Response:
        {
            "status": "healthy",
            "service": "Google ADK Agent API"
        }
    """
    return jsonify({
        'status': 'healthy',
        'service': 'Google ADK Agent API'
    })

if __name__ == '__main__':
    # Initialize agent before starting server
    logger.info("=" * 60)
    logger.info("Google ADK Agent API Server")
    logger.info("=" * 60)
    
    asyncio.run(initialize_agent())
    
    logger.info("🌐 Starting Flask + SocketIO server...")
    logger.info("🔗 Open http://localhost:5000 in your browser")
    logger.info("🔌 WebSocket: ws://localhost:5000  (event: 'chat_message')")
    logger.info("=" * 60)

    # socketio.run() replaces app.run() to enable WebSocket support
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
