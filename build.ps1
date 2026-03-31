$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$distDir = Join-Path $root "dist"
$legacyDistFolder = Join-Path $distDir "Gamer Translator"
$distExe = Join-Path $distDir "Gamer Translator.exe"
$releaseDir = Join-Path $root "release"
$releaseExe = Join-Path $releaseDir "Gamer Translator.exe"
$legacyPortableZip = Join-Path $releaseDir "Gamer Translator Portable.zip"

if (Test-Path $legacyDistFolder) {
  Remove-Item -LiteralPath $legacyDistFolder -Recurse -Force
}

if (Test-Path $distExe) {
  Remove-Item -LiteralPath $distExe -Force
}

if (Test-Path $releaseExe) {
  Remove-Item -LiteralPath $releaseExe -Force
}

if (Test-Path $legacyPortableZip) {
  Remove-Item -LiteralPath $legacyPortableZip -Force
}

python -m pip install -r requirements.txt

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "Gamer Translator" `
  --icon "gamer_translator\assets\icon.ico" `
  --add-data "gamer_translator\automation.js;gamer_translator" `
  --add-data "gamer_translator\assets\icon-128.png;gamer_translator\assets" `
  main.py

New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

Copy-Item `
  -LiteralPath $distExe `
  -Destination $releaseExe
