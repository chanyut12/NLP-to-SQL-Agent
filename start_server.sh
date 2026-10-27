#!/bin/bash

# NLP-to-SQL Agent Server Startup Script (uv-powered)
# Runs uvicorn inside the project's uv-managed venv — no manual activation needed.

set -e

echo "🚀 Starting NLP-to-SQL Agent Backend Server..."
echo ""

# ==============================================================================
# Ensure uv is available
# ==============================================================================
if ! command -v uv &> /dev/null; then
    if [ -x "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "❌ uv not found. Run ./setup.sh first, or install uv manually:"
        echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
fi

# ==============================================================================
# Ensure dependencies are synced (idempotent — fast if already up to date)
# ==============================================================================
if [ ! -d ".venv" ]; then
    echo "📦 .venv not found — running uv sync..."
    uv sync
    echo ""
fi

# ==============================================================================
# Optional: warn if Ollama is selected but not running
# ==============================================================================
if [ -f ".env" ] && grep -q "^MODEL_PROVIDER=ollama" .env; then
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "⚠️  Warning: Ollama server doesn't seem to be running"
        echo "   Start it with: ollama serve"
        echo ""
    fi
fi

# ==============================================================================
# Free port 8000: stop our launchd service automatically; refuse on strangers
# ==============================================================================
SERVICE_LABEL="com.chanyut.nlq-server"

# Only a LISTEN socket means the port is taken. Plain `lsof -ti :8000` also
# matches clients that merely have an open socket to the port — a browser tab
# or an SSH tunnel, for example — and would report a free port as busy.
listening_pids() {
    lsof -nP -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null || true
}

LISTENERS="$(listening_pids)"
if [ -n "$LISTENERS" ]; then
    if launchctl print "gui/$(id -u)/$SERVICE_LABEL" >/dev/null 2>&1; then
        echo "🔁 Port 8000 busy — stopping launchd service '$SERVICE_LABEL' first..."
        launchctl bootout "gui/$(id -u)/$SERVICE_LABEL" || true
        sleep 2
        if [ -n "$(listening_pids)" ]; then
            echo "❌ Port 8000 still busy after stopping '$SERVICE_LABEL'"
            exit 1
        fi
    else
        echo "❌ Port 8000 is used by another process:"
        for pid in $LISTENERS; do
            echo "   PID $pid  $(ps -o command= -p "$pid" 2>/dev/null | cut -c1-100)"
        done
        echo "   Stop it yourself, then re-run this script."
        exit 1
    fi
fi

echo "📡 Starting uvicorn on http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Watching directories:"
echo "  - api/ (API routes and endpoints)"
echo "  - core/ (business logic and services)"
echo ""

# API_KEY is left to .env or the shell: empty means APP_MODE=auto mounts the
# demo UI; a non-empty key means Consumer-only. For the local UI demo, use
# ./start_demo.sh; for service mode, set APP_MODE=service and API_KEY.

uv run uvicorn api.main:app \
    --reload \
    --reload-dir api \
    --reload-dir core \
    --host 0.0.0.0 \
    --port 8000
