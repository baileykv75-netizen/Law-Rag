@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [Law-Rag] Base environment not found. Run setup-dev.bat first.
  pause
  exit /b 1
)
if not exist "runtime\legal\legal.db" (
  echo [Law-Rag] Legal database not found. Run rebuild-legal-seed.bat first.
  pause
  exit /b 1
)

echo [Law-Rag] Building retrieval index with local BGE semantic vectors...
cd backend
set PYTHONPATH=.
"..\.venv\Scripts\python.exe" -m app.legal.retrieval_cli rebuild --semantic
if errorlevel 1 goto :fail

echo.
echo [Law-Rag] Hybrid retrieval index built successfully.
pause
exit /b 0

:fail
echo.
echo [Law-Rag] Hybrid retrieval index build failed.
echo Run setup-rag-semantic-cpu.bat first if semantic dependencies are missing.
pause
exit /b 1
