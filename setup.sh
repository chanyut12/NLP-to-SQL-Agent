#!/bin/bash
# ==============================================================================
# Thai NLP-to-SQL Quick Setup Script
# ==============================================================================
# This script helps you set up the project on a new machine

set -e  # Exit on error

echo "🚀 Thai NLP-to-SQL Setup Script"
echo "================================"
echo ""

# ==============================================================================
# 1. Check Python Version
# ==============================================================================
echo "📋 Step 1: Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python version must be 3.10 or higher (found: $PYTHON_VERSION)"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION detected"
echo ""

# ==============================================================================
# 2. Create Virtual Environment
# ==============================================================================
echo "📦 Step 2: Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "⚠️  Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate
echo ""

# ==============================================================================
# 3. Install Dependencies
# ==============================================================================
echo "📥 Step 3: Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# ==============================================================================
# 4. Check .env Configuration
# ==============================================================================
echo "⚙️  Step 4: Checking configuration..."
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
# 5. Check LLM Provider
# ==============================================================================
echo "🤖 Step 5: Checking LLM provider..."
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

    # Check if model is available
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
# 6. Create Sample Database
# ==============================================================================
echo "🗄️  Step 6: Creating sample database..."
if [ ! -f "local_database.db" ]; then
    python scripts/setup_db.py
    echo "✅ Sample database created"
else
    echo "⚠️  Database already exists (skipping)"
fi
echo ""

# ==============================================================================
# 7. Initialize RAG Database
# ==============================================================================
echo "🧠 Step 7: Initializing RAG database..."
if [ ! -d "rag_db" ]; then
    echo "   RAG database will be auto-created on first run"
    echo "   Source: thai_sql_examples.json"
else
    echo "✅ RAG database already exists"
fi
echo ""

# ==============================================================================
# 8. Done!
# ==============================================================================
echo "✅ Setup complete!"
echo ""
echo "🎉 You're ready to go! Start the server with:"
echo ""
echo "   # Activate virtual environment"
echo "   source venv/bin/activate"
echo ""
echo "   # Start backend server"
echo "   ./start_server.sh"
echo ""
echo "   # Then open: http://localhost:8000"
echo ""
echo "📚 For more info, see README.md"
