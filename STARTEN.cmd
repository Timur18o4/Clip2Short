@echo off
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Verwalten.ps1" -Action Start
if errorlevel 1 pause
