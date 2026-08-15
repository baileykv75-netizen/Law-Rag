@echo off
setlocal
set "ROOT=%~dp0"

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo [ERROR] Python environment not found.
  echo Run setup-dev.bat first.
  exit /b 1
)

if not exist "%ROOT%frontend\node_modules" (
  echo [ERROR] Frontend dependencies not found.
  echo Run setup-dev.bat first.
  exit /b 1
)

echo [Law-Rag] Running non-mutating runtime diagnostics ...
call "%ROOT%diagnose-runtime.bat"
if errorlevel 1 (
  echo [ERROR] Base runtime diagnostics failed. Existing runtime data was not deleted or rebuilt.
  exit /b 1
)

echo [Law-Rag] Starting local backend on http://127.0.0.1:8000 ...
start "Law-Rag Backend" cmd /k "cd /d ""%ROOT%backend"" && ""%ROOT%.venv\Scripts\python.exe"" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [Law-Rag] Starting local frontend on http://127.0.0.1:5173 ...
start "Law-Rag Frontend" cmd /k "cd /d ""%ROOT%frontend"" && npm run dev"

timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:5173

echo [Law-Rag] Two terminal windows were opened. Keep them running while using Law-Rag.
endlocal
