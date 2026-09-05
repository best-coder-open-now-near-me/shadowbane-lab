@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-wonderbane-navigation-inspector.ps1" -RuntimeDirectory "%~dp0.."
if errorlevel 1 pause
