$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$distDir = Join-Path $root "dist"
$legacyDistFolder = Join-Path $distDir "Gamer Translator"
$distExe = Join-Path $distDir "Gamer Translator.exe"

if (Test-Path $legacyDistFolder) {
  Remove-Item -LiteralPath $legacyDistFolder -Recurse -Force
}

if (Test-Path $distExe) {
  Remove-Item -LiteralPath $distExe -Force
}

python -m pip install -r requirements.txt

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --collect-all "rapidocr" `
  --collect-all "winsdk" `
  --collect-all "wordfreq" `
  --hidden-import "onnxruntime" `
  --name "Gamer Translator" `
  --icon "gamer_translator\assets\icon.ico" `
  --add-data "gamer_translator\automation.js;gamer_translator" `
  --add-data "gamer_translator\assets\icon-128.png;gamer_translator\assets" `
  main.py
