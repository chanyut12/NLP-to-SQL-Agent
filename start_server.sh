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

echo "📡 Starting uvicorn on http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Watching directories:"
echo "  - api/ (API routes and endpoints)"
echo "  - core/ (business logic and services)"
echo ""

uv run uvicorn api.main:app \
    --reload \
    --reload-dir api \
    --reload-dir core \
    --host 0.0.0.0 \
    --port 8000
