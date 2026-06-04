@echo off
cd /d "%~dp0"
set "PYTHON_CMD=python"
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"

"%PYTHON_CMD%" --version >nul 2>nul
if errorlevel 1 (
  echo Python command is not usable on this PC.
  echo Install Python 3.11 or newer, or disable the Microsoft Store python alias.
  pause
  exit /b 1
)

"%PYTHON_CMD%" run_desktop.py
pause
