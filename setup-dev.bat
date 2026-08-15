@echo off
setlocal
set "ROOT=%~dp0"

echo [Law-Rag] Checking development prerequisites...
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH.
  echo Install Python 3.11+ and run this script again.
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo [ERROR] The Python on PATH is older than 3.11.
  echo Install Python 3.11 or newer, then run this script again.
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js was not found in PATH.
  echo Install Node.js 22 LTS or another Vite 8 compatible version and run this script again.
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found in PATH.
  exit /b 1
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo [Law-Rag] Creating Python virtual environment...
  python -m venv "%ROOT%.venv"
  if errorlevel 1 exit /b 1
)

"%ROOT%.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo [ERROR] Existing .venv uses Python older than 3.11.
  echo Preserve any local data, remove/recreate only the .venv environment, then rerun setup-dev.bat.
  exit /b 1
)

echo [Law-Rag] Installing backend dependencies...
"%ROOT%.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%ROOT%.venv\Scripts\python.exe" -m pip install -r "%ROOT%backend\requirements.txt"
if errorlevel 1 exit /b 1

echo [Law-Rag] Installing frontend dependencies...
pushd "%ROOT%frontend"
npm install
if errorlevel 1 (
  popd
  exit /b 1
)
popd

echo.
echo [Law-Rag] Development setup complete.
echo Run start-dev.bat to start the local application.
endlocal & exit /b 0
