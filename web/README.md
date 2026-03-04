# Google ADK Agent Web Interface

A professional web interface for interacting with Google ADK agents.

## Project Structure

```
web/
├── app.py              # Flask API server
├── static/
│   └── index.html      # Frontend HTML/CSS/JavaScript
└── README.md           # This file
```

## Features

- 🎨 Modern, responsive chat interface
- 💬 Real-time communication with Google ADK agents
- 🛡️ Built-in guardrail validation for security
- 📝 Markdown rendering support
- 🔒 Error handling and validation

## Installation

1. Make sure you have the required dependencies:
   ```powershell
   pip install -r ../requirements.txt
   ```

2. Ensure your `.env` file is configured with necessary API keys

## Running the Server

From the `web` directory:

```powershell
python app.py
```

Or from the project root:

```powershell
python web/app.py
```

The server will start on `http://localhost:5000`

## API Endpoints

### `POST /api/chat`
Send a message to the agent.

**Request:**
```json
{
    "message": "Your message here"
}
```

**Response:**
```json
{
    "response": "Agent's response",
    "status": "success"
}
```

### `GET /api/health`
Check server health status.

**Response:**
```json
{
    "status": "healthy",
    "service": "Google ADK Agent API"
}
```

## Development

- **Frontend**: Edit `static/index.html` for UI changes
- **Backend**: Edit `app.py` for API logic changes
- **Agents**: Edit `../GoogleADK/agent.py` for agent configuration

## Notes

- The server runs in debug mode by default for development
- For production, set `debug=False` in `app.py`
- The typewriter effect speed can be adjusted in `index.html` (default: 20ms per character)
