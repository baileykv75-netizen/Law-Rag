@echo off
setlocal
cd /d "%~dp0"

echo [Law-Rag] DEVELOPMENT / SOURCE-CHECKOUT HELPER ONLY.
echo The packaged Windows release already includes the PaddlePaddle/PaddleOCR runtime.
echo End users of the portable bundle should NOT run this script.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [Law-Rag] Base development environment not found.
  echo Run setup-dev.bat first, then run this script again.
  pause
  exit /b 1
)

echo [Law-Rag] Installing PaddlePaddle 3.3.0 CPU build from the official index into the development venv...
".venv\Scripts\python.exe" -m pip install paddlepaddle==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
if errorlevel 1 goto :fail

echo [Law-Rag] Installing PaddleOCR 3.7.0 development dependencies...
".venv\Scripts\python.exe" -m pip install -r backend\requirements-ocr.txt
if errorlevel 1 goto :fail

echo [Law-Rag] Verifying PaddlePaddle and PaddleOCR imports...
".venv\Scripts\python.exe" -c "import paddle, paddleocr; paddle.utils.run_check(); print('PaddleOCR', paddleocr.__version__)"
if errorlevel 1 goto :fail

echo.
echo [Law-Rag] Development OCR runtime installed successfully.
echo [Law-Rag] NOTE: Stage 14.4 packages the runtime only. Fixed/offline PP-OCR model
echo [Law-Rag] distribution is Stage 14.5; this helper does not define the release model boundary.
pause
exit /b 0

:fail
echo.
echo [Law-Rag] Development OCR setup failed. Review the error above.
pause
exit /b 1
