@echo off
setlocal
set "ROOT=%~dp0"

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo [ERROR] Python environment not found.
  echo Run setup-dev.bat first.
  exit /b 1
)

cd /d "%ROOT%backend"
"%ROOT%.venv\Scripts\python.exe" -m app.runtime_health_cli
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [Law-Rag] Base runtime is not ready. Diagnostics above did not delete or rebuild any data.
)

endlocal & exit /b %EXIT_CODE%
