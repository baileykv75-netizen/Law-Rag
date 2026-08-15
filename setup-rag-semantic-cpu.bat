@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [Law-Rag] Base environment not found.
  echo Run setup-dev.bat first, then run this script again.
  pause
  exit /b 1
)

echo [Law-Rag] Installing optional local semantic retrieval dependencies...
".venv\Scripts\python.exe" -m pip install -r backend\requirements-rag.txt
if errorlevel 1 goto :fail

echo [Law-Rag] Verifying sentence-transformers...
".venv\Scripts\python.exe" -c "import sentence_transformers; print('sentence-transformers', sentence_transformers.__version__)"
if errorlevel 1 goto :fail

echo.
echo [Law-Rag] Semantic runtime installed successfully.
echo BAAI/bge-small-zh-v1.5 model files will download on first semantic index build.
pause
exit /b 0

:fail
echo.
echo [Law-Rag] Semantic retrieval setup failed. Review the error above.
pause
exit /b 1
