param([string]$NodePath = (Get-Command node -ErrorAction Stop).Source)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$webRoot = Join-Path $taskRoot 'web'
$logRoot = Join-Path $taskRoot 'tmp/intelligence-web'
if (Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue) {
  throw 'Port 5174 is already in use. Keep the existing candidate or stop its verified process first.'
}
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$env:STL_DEMO_API_URL = 'http://192.168.5.6:18091'
$env:INTERNAL_API_URL = "$env:STL_DEMO_API_URL/api"
$env:ALLOW_DEMO_FALLBACK = 'false'
$env:WRANGLER_WRITE_LOGS = 'false'
$process = Start-Process -FilePath $NodePath -ArgumentList @('node_modules/vite/bin/vite.js', '--config', 'vite.intelligence-demo.config.ts') -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'stdout.log') -RedirectStandardError (Join-Path $logRoot 'stderr.log')
@{ pid = $process.Id; workspace = $taskRoot; url = 'http://192.168.5.3:5174'; started = (Get-Date -Format o) } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logRoot 'process.json') -Encoding utf8
Write-Output "Started isolated LAN candidate process $($process.Id). Logs: $logRoot"
