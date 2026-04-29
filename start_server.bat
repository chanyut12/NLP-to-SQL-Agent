@echo off
REM NLP-to-SQL Agent Server Startup Script (Windows, uv-powered)
REM Runs uvicorn inside the project's uv-managed venv - no manual activation needed.

echo.
echo Starting NLP-to-SQL Agent Backend Server...
echo.

REM ==============================================================================
REM Ensure uv is available
REM ==============================================================================
where uv >nul 2>&1
if errorlevel 1 (
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    ) else (
        echo [ERROR] uv not found. Run setup.bat first, or install uv manually:
        echo   powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
        pause
        exit /b 1
    )
)

REM ==============================================================================
REM Ensure dependencies are synced
REM ==============================================================================
if not exist ".venv" (
    echo [INFO] .venv not found - running uv sync...
    uv sync
    echo.
)

echo Starting uvicorn on http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.
echo Watching directories:
echo   - api/ (API routes and endpoints)
echo   - core/ (business logic and services)
echo.

uv run uvicorn api.main:app ^
    --reload ^
    --reload-dir api ^
    --reload-dir core ^
    --host 0.0.0.0 ^
    --port 8000
