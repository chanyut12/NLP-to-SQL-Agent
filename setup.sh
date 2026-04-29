#!/bin/bash
# ==============================================================================
# Thai NLP-to-SQL Quick Setup Script (uv-powered)
# ==============================================================================
# Works on macOS and Linux. Requires `uv` (https://docs.astral.sh/uv/).

set -e

echo "🚀 Thai NLP-to-SQL Setup Script"
echo "================================"
echo ""

# ==============================================================================
# 1. Check / install uv
# ==============================================================================
echo "📋 Step 1: Checking uv..."
if ! command -v uv &> /dev/null; then
    echo "⚠️  uv not found. Installing via official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1090
    source "$HOME/.local/bin/env" 2>/dev/null || export PATH="$HOME/.local/bin:$PATH"
fi
echo "✅ uv $(uv --version | awk '{print $2}') ready"
echo ""

# ==============================================================================
# 2. Sync dependencies (creates .venv automatically)
# ==============================================================================
echo "📥 Step 2: Installing dependencies with uv sync..."
uv sync
echo "✅ Dependencies installed in .venv/"
echo ""

# ==============================================================================
# 3. Check .env Configuration
# ==============================================================================
echo "⚙️  Step 3: Checking configuration..."
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from template..."
    cp .env.example .env
    echo "✅ .env file created from template"
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env file and configure your LLM provider:"
    echo "   - For local: Install Ollama and run: ollama pull qwen2.5-coder:7b"
    echo "   - For cloud: Add your API key (Google Gemini or OpenAI)"
    echo ""
    read -p "Press Enter to continue after configuring .env..."
else
    echo "✅ .env file exists"
fi
echo ""

# ==============================================================================
# 4. Check LLM Provider
# ==============================================================================
echo "🤖 Step 4: Checking LLM provider..."
MODEL_PROVIDER=$(grep "^MODEL_PROVIDER" .env | cut -d'=' -f2 | tr -d ' "' | head -1)

if [ "$MODEL_PROVIDER" = "ollama" ]; then
    echo "🔍 Checking Ollama installation..."
    if ! command -v ollama &> /dev/null; then
        echo "❌ Ollama not found!"
        echo "   Please install Ollama from: https://ollama.com/"
        echo "   Then run: ollama pull qwen2.5-coder:7b"
        exit 1
    fi

    echo "✅ Ollama found"

    OLLAMA_MODEL=$(grep "^OLLAMA_MODEL" .env | cut -d'=' -f2 | tr -d ' "' | head -1)
    if ! ollama list | grep -q "$OLLAMA_MODEL"; then
        echo "⚠️  Model $OLLAMA_MODEL not found locally"
        echo "   Downloading... (this may take 5-15 minutes)"
        ollama pull "$OLLAMA_MODEL"
        echo "✅ Model downloaded"
    else
        echo "✅ Model $OLLAMA_MODEL is ready"
    fi
elif [ "$MODEL_PROVIDER" = "google" ]; then
    echo "✅ Using Google Gemini (cloud)"
elif [ "$MODEL_PROVIDER" = "openai" ]; then
    echo "✅ Using OpenAI (cloud)"
else
    echo "⚠️  Unknown MODEL_PROVIDER: $MODEL_PROVIDER"
fi
echo ""

# ==============================================================================
# 5. Create Sample Database
# ==============================================================================
echo "🗄️  Step 5: Creating sample database..."
if [ ! -f "local_database.db" ]; then
    uv run python scripts/setup_db.py
    echo "✅ Sample database created"
else
    echo "⚠️  Database already exists (skipping)"
fi
echo ""

# ==============================================================================
# 6. Done!
# ==============================================================================
echo "✅ Setup complete!"
echo ""
echo "🎉 Start the server with:"
echo ""
echo "   ./start_server.sh"
echo ""
echo "   (no need to activate venv — uv run handles it)"
echo ""
echo "📚 For more info, see README.md"
