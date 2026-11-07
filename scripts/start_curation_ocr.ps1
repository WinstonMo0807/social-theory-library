param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'tmp/stl4-local-ocr-20261106/venv/Scripts/python.exe'
$service = Join-Path $PSScriptRoot 'curation_ocr_service.py'
$evidence = Join-Path $projectRoot 'tmp/nas-optimize-20261108'
foreach ($path in @($python,$service,(Join-Path $projectRoot 'tmp/stl4-rapidocr-20261027/models/PP-OCRv6_rec_tiny.onnx'))) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required local OCR file missing: $path" }
}
if ($CheckOnly) { Write-Output 'Local OCR launch prerequisites exist; no service started.'; exit 0 }
if (Get-NetTCPConnection -LocalPort 18091 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 18091 is already listening. Check the existing service instead of starting another copy.'
}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$process=Start-Process -FilePath $python -ArgumentList @('"'+$service+'"') -WindowStyle Hidden -WorkingDirectory $projectRoot `
    -RedirectStandardOutput (Join-Path $evidence "curation-ocr-$stamp.out.log") `
    -RedirectStandardError (Join-Path $evidence "curation-ocr-$stamp.err.log") -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $evidence 'local-ocr.pid')
Write-Output "Local OCR started with PID $($process.Id). NAS tasks remain paused until the explicit resume command."
