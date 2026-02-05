@echo off
REM NLP-to-SQL Agent Server Startup Script (Windows)
REM This script starts the FastAPI server with proper file watching exclusions

echo.
echo Starting NLP-to-SQL Agent Backend Server...
echo.

REM Check if virtual environment is activated
if not defined VIRTUAL_ENV (
    echo Warning: Virtual environment not detected
    echo Activate it first with: venv\Scripts\activate
    echo.
    pause
)

REM Start uvicorn with proper file watching
echo Starting uvicorn on http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.
echo Watching directories:
echo   - api/ (API routes and endpoints)
echo   - core/ (business logic and services)
echo.
echo This prevents reload loops from venv changes
echo.

uvicorn api.main:app ^
    --reload ^
    --reload-dir api ^
    --reload-dir core ^
    --host 0.0.0.0 ^
    --port 8000
