#!/bin/bash

# Standalone demo server.
#
# This mode is intentionally local-only: the web UI is served at / and /api is
# unauthenticated. It uses the bundled SQLite sample, never the production
# DATABASE_URL from .env. For the Consumer-only microservice, use
# ./start_server.sh with APP_MODE=service and a real API_KEY.

set -e

cd "$(dirname "$0")"

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

if [ ! -d ".venv" ]; then
    echo "📦 .venv not found — running uv sync..."
    uv sync
    echo ""
fi

if [ ! -f "local_database.db" ]; then
    echo "🗄️  local_database.db not found — creating the sample database..."
    uv run python scripts/setup_db.py
    echo ""
fi

PORT="${DEMO_PORT:-8001}"
HOST="${DEMO_HOST:-127.0.0.1}"

# Only a LISTEN socket means the port is taken. Plain `lsof -ti :$PORT` also
# matches clients that merely have an open socket to the port — a browser tab
# still pointed at a server that already stopped, for example — and would
# report a free port as busy.
if command -v lsof >/dev/null 2>&1; then
    LISTENING_PIDS="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [ -n "$LISTENING_PIDS" ]; then
        echo "❌ Port $PORT is already in use by:"
        for pid in $LISTENING_PIDS; do
            echo "   PID $pid  $(ps -o command= -p "$pid" 2>/dev/null | cut -c1-100)"
        done
        echo "   Stop that process or set DEMO_PORT to another port."
        exit 1
    fi
fi

# Export values win over .env (python-dotenv does not override existing env),
# so this demo can never accidentally point at the production STS datasource.
export APP_MODE=demo
export API_KEY=""
export DATABASE_URL="${DEMO_DATABASE_URL:-sqlite:///./local_database.db}"
export DOMAIN_PROFILE="${DEMO_DOMAIN_PROFILE:-demo}"

echo "🧪 Starting standalone demo"
echo "   UI:       http://$HOST:$PORT/"
echo "   Database: $DATABASE_URL"
echo "   Profile:  $DOMAIN_PROFILE"
echo "   Host:     $HOST:$PORT (local-only by default)"
echo ""

uv run uvicorn api.main:app \
    --reload \
    --reload-dir api \
    --reload-dir core \
    --host "$HOST" \
    --port "$PORT"
