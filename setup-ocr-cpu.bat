@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [Law-Rag] Base environment not found.
  echo Run setup-dev.bat first, then run this script again.
  pause
  exit /b 1
)

echo [Law-Rag] Installing PaddlePaddle 3.3.0 CPU build from the official index...
".venv\Scripts\python.exe" -m pip install paddlepaddle==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
if errorlevel 1 goto :fail

echo [Law-Rag] Installing PaddleOCR 3.7.0...
".venv\Scripts\python.exe" -m pip install -r backend\requirements-ocr.txt
if errorlevel 1 goto :fail

echo [Law-Rag] Verifying PaddlePaddle and PaddleOCR imports...
".venv\Scripts\python.exe" -c "import paddle, paddleocr; paddle.utils.run_check(); print('PaddleOCR', paddleocr.__version__)"
if errorlevel 1 goto :fail

echo.
echo [Law-Rag] OCR runtime installed successfully.
echo Models are downloaded on first OCR use. If Hugging Face is inaccessible,
echo set PADDLE_PDX_MODEL_SOURCE=BOS before starting Law-Rag.
pause
exit /b 0

:fail
echo.
echo [Law-Rag] OCR setup failed. Review the error above.
pause
exit /b 1
