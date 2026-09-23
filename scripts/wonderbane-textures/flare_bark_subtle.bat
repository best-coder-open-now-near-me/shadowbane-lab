@echo off
setlocal
if "%~1"=="" (
  echo Drag an extracted bark or mixed tree texture onto this file.
  pause
  exit /b 2
)
set "OUT=%~dpn1_flared_subtle.png"
py -3 "%~dp0wonderbane_texture_flare.py" "%~1" "%OUT%" --mode bark --preset subtle --preview "%~dpn1_flared_subtle_preview.png" --report "%~dpn1_flared_subtle.report.json"
if errorlevel 1 python "%~dp0wonderbane_texture_flare.py" "%~1" "%OUT%" --mode bark --preset subtle --preview "%~dpn1_flared_subtle_preview.png" --report "%~dpn1_flared_subtle.report.json"
pause
