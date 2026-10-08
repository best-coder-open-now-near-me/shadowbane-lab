@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-ShadowbaneLocal.ps1" %*
if errorlevel 1 echo Update did not finish. Read the error above before trying again.
pause
