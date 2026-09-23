@echo off
setlocal
if "%~1"=="" (
  echo Drag a pure-black color-key foliage texture onto this file.
  pause
  exit /b 2
)
set "OUT=%~dpn1_flared_subtle_blackkey.png"
py -3 "%~dp0wonderbane_texture_flare.py" "%~1" "%OUT%" --mode foliage --preset subtle --key black --output-mode black-key --preview "%~dpn1_flared_subtle_blackkey_preview.png" --report "%~dpn1_flared_subtle_blackkey.report.json"
if errorlevel 1 python "%~dp0wonderbane_texture_flare.py" "%~1" "%OUT%" --mode foliage --preset subtle --key black --output-mode black-key --preview "%~dpn1_flared_subtle_blackkey_preview.png" --report "%~dpn1_flared_subtle_blackkey.report.json"
pause
