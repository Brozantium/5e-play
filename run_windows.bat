@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found.
  echo Follow docs\WINDOWS.md to create .venv and install the dependencies.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run_scrape.py %*
echo.
echo Finished. Check the output, exports, and logs folders.
pause
