@echo off
REM ==============================================================================
REM Thai NLP-to-SQL Quick Setup Script (Windows, uv-powered)
REM ==============================================================================

echo =================================
echo Thai NLP-to-SQL Setup Script
echo =================================
echo.

REM ==============================================================================
REM 1. Check / install uv
REM ==============================================================================
echo [Step 1] Checking uv...
where uv >nul 2>&1
if errorlevel 1 (
    echo [WARN] uv not found. Installing via official installer...
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

uv --version
if errorlevel 1 (
    echo [ERROR] uv install failed. Install manually from https://docs.astral.sh/uv/
    pause
    exit /b 1
)
echo [OK] uv ready
echo.

REM ==============================================================================
REM 2. Sync dependencies
REM ==============================================================================
echo [Step 2] Installing dependencies with uv sync...
uv sync
if errorlevel 1 (
    echo [ERROR] uv sync failed
    pause
    exit /b 1
)
echo [OK] Dependencies installed in .venv\
echo.

REM ==============================================================================
REM 3. Check .env Configuration
REM ==============================================================================
echo [Step 3] Checking configuration...
if not exist ".env" (
    echo [WARN] No .env file found. Creating from template...
    copy .env.example .env
    echo [OK] .env file created
    echo.
    echo [IMPORTANT] Please edit .env file and configure your LLM provider:
    echo   - For local: Install Ollama and run: ollama pull qwen2.5-coder:7b
    echo   - For cloud: Add your API key (Google Gemini or OpenAI)
    echo.
    pause
) else (
    echo [OK] .env file exists
)
echo.

REM ==============================================================================
REM 4. Check LLM Provider
REM ==============================================================================
echo [Step 4] Checking LLM provider...
for /f "tokens=2 delims==" %%i in ('findstr /b "MODEL_PROVIDER" .env') do set MODEL_PROVIDER=%%i

if "%MODEL_PROVIDER%"=="ollama" (
    echo [CHECK] Checking Ollama installation...
    where ollama >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Ollama not found!
        echo   Please install Ollama from: https://ollama.com/
        echo   Then run: ollama pull qwen2.5-coder:7b
        pause
        exit /b 1
    )
    echo [OK] Ollama found
) else (
    echo [OK] Using cloud provider: %MODEL_PROVIDER%
)
echo.

REM ==============================================================================
REM 5. Create Sample Database
REM ==============================================================================
echo [Step 5] Creating sample database...
if not exist "local_database.db" (
    uv run python scripts\setup_db.py
    echo [OK] Sample database created
) else (
    echo [SKIP] Database already exists
)
echo.

REM ==============================================================================
REM 6. Done!
REM ==============================================================================
echo ========================================
echo [SUCCESS] Setup complete!
echo ========================================
echo.
echo Start the server with:
echo.
echo   start_server.bat
echo.
echo   (no need to activate venv - uv run handles it)
echo.
echo For more info, see README.md
echo.
pause
