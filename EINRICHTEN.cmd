@echo off
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0Installieren.ps1"
