@echo off
if "%1"=="elevated" goto run
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
    exit /b
)
:run
chcp 65001 >nul
cd /d "%~dp0"
netsh advfirewall firewall show rule name="CDE Studio Port 80" >nul 2>&1
if %errorlevel% neq 0 (
    netsh advfirewall firewall add rule name="CDE Studio Port 80" dir=in action=allow protocol=TCP localport=80 >nul
)
python run.py
pause
