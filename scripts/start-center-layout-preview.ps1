param(
    [string]$Python = 'C:/Python314/python.exe',
    [string]$PythonDependencies = 'F:/agent skills/书库开发3/.venv/Lib/site-packages'
)
$ErrorActionPreference = 'Stop'
$previewRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $previewRoot 'output/public-visual-20261110/runtime'
$fixtureFile = Join-Path $previewRoot 'output/public-visual-20261110/audit/FIXTURE_RUNTIME.json'
$fixture = Get-Content -LiteralPath $fixtureFile -Raw | ConvertFrom-Json
if ($fixture.offline -ne $true -or $fixture.api_url -ne 'http://127.0.0.1:18111/api' -or $fixture.web_url -ne 'http://127.0.0.1:18110') {
    throw 'Only the recorded offline local preview may be started.'
}
if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 18110,18111 }) {
    throw 'A preview port is already in use. Inspect its owner; do not stop other services.'
}
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$env:PYTHONPATH = $PythonDependencies
$env:PYTHONUTF8 = '1'
$env:STL_E2E_V307 = '0'

function Wait-PreviewHttp([string]$Url, [Diagnostics.Process]$Process) {
    $deadline = (Get-Date).AddSeconds(45)
    do {
        $Process.Refresh()
        if ($Process.HasExited) { throw "Preview process exited: $($Process.ExitCode). Check local logs." }
        try {
            if ((Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Preview did not become ready: $Url. Check local logs; processes were not killed."
}

$apiProcess = Start-Process -FilePath $Python -ArgumentList @('-u','scripts/local_cataloging_e2e_api.py','--api-port','18111','--web-port','18110','--offline','--resume-ready-file','output/public-visual-20261110/audit/FIXTURE_RUNTIME.json') -WorkingDirectory $previewRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDir 'api-background.out.log') -RedirectStandardError (Join-Path $runtimeDir 'api-background.err.log') -PassThru
Wait-PreviewHttp 'http://127.0.0.1:18111/api/health/' $apiProcess
$webProcess = Start-Process -FilePath (Get-Command node).Source -ArgumentList @('scripts/start_center_layout_preview.mjs') -WorkingDirectory $previewRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDir 'web-background.out.log') -RedirectStandardError (Join-Path $runtimeDir 'web-background.err.log') -PassThru
Wait-PreviewHttp 'http://127.0.0.1:18110/login' $webProcess
@{ apiPid=$apiProcess.Id; webPid=$webProcess.Id; api='http://127.0.0.1:18111/api'; web='http://127.0.0.1:18110'; mode='offline existing fixture'; startedAt=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'background-processes.json') -Encoding utf8
Write-Output 'Both independent background processes are ready. Existing fixture data and credentials are preserved.'
