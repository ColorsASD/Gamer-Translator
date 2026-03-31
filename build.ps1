$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m pip install -r requirements.txt

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name "Gamer Translator" `
  --icon "gamer_translator\assets\icon.ico" `
  --add-data "gamer_translator\automation.js;gamer_translator" `
  --add-data "gamer_translator\assets\icon-128.png;gamer_translator\assets" `
  main.py
