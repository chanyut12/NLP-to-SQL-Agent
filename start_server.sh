#!/bin/bash

# NLP-to-SQL Agent Server Startup Script
# This script starts the FastAPI server with proper file watching exclusions
# to prevent infinite reload loops from virtual environment changes

echo "🚀 Starting NLP-to-SQL Agent Backend Server..."
echo ""

# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "⚠️  Warning: Virtual environment not detected"
    echo "   Activate it first with: source venv/bin/activate"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "⚠️  Warning: Ollama server doesn't seem to be running"
    echo "   Start it with: ollama serve"
    echo ""
fi

# Start uvicorn with proper file watching
echo "📡 Starting uvicorn on http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Watching directories:"
echo "  - api/ (API routes and endpoints)"
echo "  - core/ (business logic and services)"
echo ""
echo "✅ This prevents reload loops from venv changes"
echo ""

uvicorn api.main:app \
    --reload \
    --reload-dir api \
    --reload-dir core \
    --host 0.0.0.0 \
    --port 8000
