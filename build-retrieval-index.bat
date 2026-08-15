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

echo [Law-Rag] Rebuilding exact/FTS5-trigram lexical retrieval index...
cd backend
set PYTHONPATH=.
"..\.venv\Scripts\python.exe" -m app.legal.retrieval_cli rebuild
if errorlevel 1 goto :fail

echo.
echo [Law-Rag] Retrieval index built successfully.
pause
exit /b 0

:fail
echo.
echo [Law-Rag] Retrieval index build failed. Review the error above.
pause
exit /b 1
