@echo off
setlocal
py -3 "%~dp0selftest.py"
if errorlevel 1 python "%~dp0selftest.py"
pause
