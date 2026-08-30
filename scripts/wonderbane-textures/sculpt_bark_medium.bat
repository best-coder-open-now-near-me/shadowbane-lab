@echo off
setlocal
if "%~1"=="" (
  echo Drag a bark source texture onto this file.
  pause
  exit /b 2
)
py -3 "%~dp0wonderbane_texture_sculptor.py" "%~1" "%~dp1sculpted" --mode bark --sizes 256 128 --strength medium
if errorlevel 1 python "%~dp0wonderbane_texture_sculptor.py" "%~1" "%~dp1sculpted" --mode bark --sizes 256 128 --strength medium
pause
