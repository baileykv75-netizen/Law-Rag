@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [Law-Rag] Python environment not found. Run setup-dev.bat first.
  pause
  exit /b 1
)

cd backend
set PYTHONPATH=.
"..\.venv\Scripts\python.exe" -m app.legal.cli rebuild --manifest "..\legal_data\seed\manifest.json"
set EXIT_CODE=%ERRORLEVEL%
cd ..

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [Law-Rag] Legal seed rebuild failed. See runtime\legal\import_reports\last-import-report.json
  pause
  exit /b %EXIT_CODE%
)

echo.
echo [Law-Rag] Legal seed database rebuilt successfully at runtime\legal\legal.db
pause
