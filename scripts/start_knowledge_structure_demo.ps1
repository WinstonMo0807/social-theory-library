param(
  [Parameter(Mandatory=$true)][string]$PythonPath,
  [Parameter(Mandatory=$true)][string]$ModelsPath,
  [Parameter(Mandatory=$true)][string]$WorkerTokenFile,
  [Parameter(Mandatory=$true)][string]$ServerCertificate,
  [string]$ParserPackageRoot = ''
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = (Resolve-Path -LiteralPath $PythonPath).Path
$models = (Resolve-Path -LiteralPath $ModelsPath).Path
$tokenFile = (Resolve-Path -LiteralPath $WorkerTokenFile).Path
$certificate = (Resolve-Path -LiteralPath $ServerCertificate).Path
$priorPythonPath = $env:PYTHONPATH
if ($ParserPackageRoot) {
  $parserRoot = (Resolve-Path -LiteralPath $ParserPackageRoot).Path
  if ($parserRoot -match '[^\x00-\x7F]' -or !(Test-Path -LiteralPath (Join-Path $parserRoot 'docling_parse/pdf_resources/glyphs/standard/additional.dat'))) {
    throw 'Docling native resources require the matching installed package at an ASCII path.'
  }
}
$logRoot = Join-Path $taskRoot 'tmp/structure-worker'
$processFile = Join-Path $logRoot 'process.json'
if (Test-Path -LiteralPath $processFile) {
  $prior = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
  if (Get-Process -Id $prior.worker_pid -ErrorAction SilentlyContinue) {
    throw 'A recorded worker process still exists. Verify it before starting another executor.'
  }
}
$token = [IO.File]::ReadAllText($tokenFile).Trim()
if ($token.Length -lt 32) { throw 'The executor credential is missing or incomplete.' }
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
try {
  $env:STL_WORKER_SERVER_URL = 'https://192.168.5.6:18491/api/capability-worker'
  $env:STL_WORKER_CA_FILE = $certificate
  $env:STL_WORKER_TOKEN = $token
  $env:STL_WORKER_EXECUTOR_ID = 'stl-demo-windows-structure'
  $env:STL_WORKER_DISPLAY_NAME = '内网正文结构解析'
  $env:STL_WORKER_GPU_NAME = ''
  $env:STL_WORKER_CAPABILITIES = 'document_parse'
  $env:STL_WORKER_TASK_KINDS = 'document_structure'
  $env:STL_WORKER_CONCURRENCY = '1'
  $env:STL_WORKER_ALLOW_HTTP = 'false'
  $env:STL_WORKER_POLL_SECONDS = '20'
  $env:STL_DOCLING_ARTIFACTS = $models
  $env:PYTHONUTF8 = '1'
  if ($ParserPackageRoot) { $env:PYTHONPATH = (@($parserRoot, $priorPythonPath) | Where-Object { $_ }) -join [IO.Path]::PathSeparator }
  $worker = Start-Process -FilePath $python -ArgumentList @('-u', '-m', 'common.remote_worker_client') `
    -WorkingDirectory (Join-Path $taskRoot 'api') -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logRoot 'worker.stdout.log') -RedirectStandardError (Join-Path $logRoot 'worker.stderr.log')
  @{ worker_pid = $worker.Id; workspace = $taskRoot; started = (Get-Date -Format o) } |
    ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding utf8
  Write-Output "Started structure worker $($worker.Id). Logs: $logRoot"
} finally {
  Remove-Item Env:STL_WORKER_TOKEN -ErrorAction SilentlyContinue
  $env:PYTHONPATH = $priorPythonPath
  $token = $null
}
