$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$distDir = Join-Path $root "dist"
$distExe = Join-Path $distDir "Gamer Translator.exe"
$legacyDistFolder = Join-Path $distDir "Gamer Translator"
$workDir = Join-Path $distDir ".build"
$specDir = Join-Path $distDir ".spec"
$rootSpec = Join-Path $root "Gamer Translator.spec"
$mainScript = Join-Path $root "main.py"
$iconFile = Join-Path $root "gamer_translator\assets\icon.ico"
$icon128File = Join-Path $root "gamer_translator\assets\icon-128.png"
$automationScript = Join-Path $root "gamer_translator\automation.js"

if (-not (Test-Path $distDir)) {
  New-Item -ItemType Directory -Path $distDir | Out-Null
}

if (Test-Path $legacyDistFolder) {
  Remove-Item -LiteralPath $legacyDistFolder -Recurse -Force
}

foreach ($cleanupPath in @($distExe, $workDir, $specDir, $rootSpec)) {
  if (Test-Path $cleanupPath) {
    Remove-Item -LiteralPath $cleanupPath -Recurse -Force
  }
}

Get-ChildItem -LiteralPath $distDir -Filter *.exe -File -ErrorAction SilentlyContinue | Remove-Item -Force

python -m pip install -r requirements.txt

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --distpath "$distDir" `
  --workpath "$workDir" `
  --specpath "$specDir" `
  --collect-all "rapidocr" `
  --collect-all "winsdk" `
  --collect-all "wordfreq" `
  --hidden-import "onnxruntime" `
  --name "Gamer Translator" `
  --icon "$iconFile" `
  --add-data "${automationScript};gamer_translator" `
  --add-data "${icon128File};gamer_translator\assets" `
  "$mainScript"

foreach ($cleanupPath in @($legacyDistFolder, $workDir, $specDir, $rootSpec)) {
  if (Test-Path $cleanupPath) {
    Remove-Item -LiteralPath $cleanupPath -Recurse -Force
  }
}
