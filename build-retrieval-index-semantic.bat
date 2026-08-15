@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo [Law-Rag] Base environment not found. Run setup-dev.bat first.
  pause
  exit /b 1
)

pushd "%ROOT%backend"
set PYTHONPATH=.
"%ROOT%.venv\Scripts\python.exe" -c "from app.storage import legal_db_path; import sys; p=legal_db_path(); print('[Law-Rag] legal.db:', p); raise SystemExit(0 if p.exists() else 1)"
if errorlevel 1 (
  popd
  echo [Law-Rag] Legal database not found at the configured path.
  echo Run rebuild-legal-seed.bat or correct LAW_RAG_LEGAL_DB, then try again.
  pause
  exit /b 1
)

echo [Law-Rag] Building retrieval index with local BGE semantic vectors...
"%ROOT%.venv\Scripts\python.exe" -m app.legal.retrieval_cli rebuild --semantic
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [Law-Rag] Hybrid retrieval index build failed. Existing legal.db was not deleted.
  echo Run setup-rag-semantic-cpu.bat first if semantic dependencies are missing.
  pause
  exit /b %EXIT_CODE%
)

echo.
echo [Law-Rag] Hybrid retrieval index built successfully.
pause
endlocal & exit /b 0
