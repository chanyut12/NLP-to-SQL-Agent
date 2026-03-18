@echo off
REM ==============================================================================
REM Thai NLP-to-SQL Quick Setup Script (Windows)
REM ==============================================================================

echo =================================
echo Thai NLP-to-SQL Setup Script
echo =================================
echo.

REM ==============================================================================
REM 1. Check Python
REM ==============================================================================
echo [Step 1] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% detected
echo.

REM ==============================================================================
REM 2. Create Virtual Environment
REM ==============================================================================
echo [Step 2] Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    echo [OK] Virtual environment created
) else (
    echo [SKIP] Virtual environment already exists
)

REM Activate virtual environment
call venv\Scripts\activate.bat
echo.

REM ==============================================================================
REM 3. Install Dependencies
REM ==============================================================================
echo [Step 3] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo [OK] Dependencies installed
echo.

REM ==============================================================================
REM 4. Check .env Configuration
REM ==============================================================================
echo [Step 4] Checking configuration...
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
REM 5. Check LLM Provider
REM ==============================================================================
echo [Step 5] Checking LLM provider...
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
REM 6. Create Sample Database
REM ==============================================================================
echo [Step 6] Creating sample database...
if not exist "local_database.db" (
    python scripts\setup_db.py
    echo [OK] Sample database created
) else (
    echo [SKIP] Database already exists
)
echo.

REM ==============================================================================
REM 7. Done!
REM ==============================================================================
echo ========================================
echo [SUCCESS] Setup complete!
echo ========================================
echo.
echo You can now start the server:
echo.
echo   1. Activate virtual environment:
echo      venv\Scripts\activate
echo.
echo   2. Start backend server:
echo      uvicorn api.main:app --reload
echo.
echo   3. Open: http://localhost:8000
echo.
echo For more info, see README.md
echo.
pause
