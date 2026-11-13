param(
    [string]$Python = 'C:/Python314/python.exe',
    [string]$PythonDependencies = 'F:/agent skills/书库开发3/.venv/Lib/site-packages',
    [string]$Node = '',
    [switch]$DetachedWorker
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
if (-not $Node) { $Node = (Get-Command node).Source }
$stateFile = Join-Path $runtimeDir 'background-processes.json'
$eventFile = Join-Path $runtimeDir 'background-events.jsonl'
if (-not $DetachedWorker) {
    # WMI owns the launcher process, rather than the temporary caller's tree.
    # No scheduled task, Windows service, logon item or elevated account is added.
    foreach ($value in @($PSCommandPath,$Python,$PythonDependencies,$Node)) {
        if ($value.Contains('"') -or $value.Contains("`n") -or $value.Contains("`r")) { throw 'Invalid executable or script path.' }
    }
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow=[uint16]0 }
    $shellPath = (Get-Process -Id $PID).Path
    $command = '"{0}" -NoProfile -NonInteractive -WindowStyle Hidden -File "{1}" -DetachedWorker -Python "{2}" -PythonDependencies "{3}" -Node "{4}"' -f $shellPath,$PSCommandPath,$Python,$PythonDependencies,$Node
    $launched = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$command;CurrentDirectory=$previewRoot;ProcessStartupInformation=$startup}
    if ($launched.ReturnValue -ne 0) { throw "Independent launcher failed: $($launched.ReturnValue)" }
    $deadline = (Get-Date).AddSeconds(50)
    do {
        if (Test-Path -LiteralPath $stateFile) {
            $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            if ($state.supervisorPid -eq $launched.ProcessId -and $state.ready) {
                Write-Output "Independent preview supervisor ready (PID $($launched.ProcessId))."
                return
            }
        }
        if (-not (Get-Process -Id $launched.ProcessId -ErrorAction SilentlyContinue)) { throw 'Independent launcher exited; check background-events.jsonl.' }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw 'Independent launcher is still starting; inspect its logs before another launch.'
}
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

function Write-PreviewEvent([string]$Kind, $Details) {
    @{time=(Get-Date).ToString('o');kind=$Kind;details=$Details} | ConvertTo-Json -Compress | Add-Content -LiteralPath $eventFile -Encoding utf8
}
function Start-PreviewChild([string]$Kind) {
    $port = if ($Kind -eq 'api') {18111} else {18110}
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is occupied; no other process will be stopped." }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $executable = if ($Kind -eq 'api') {$Python} else {$Node}
    $arguments = if ($Kind -eq 'api') {@('-u','scripts/local_cataloging_e2e_api.py','--api-port','18111','--web-port','18110','--offline','--resume-ready-file','output/public-visual-20261110/audit/FIXTURE_RUNTIME.json')} else {@('scripts/start_center_layout_preview.mjs')}
    $child = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $previewRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDir "$Kind-$stamp.out.log") -RedirectStandardError (Join-Path $runtimeDir "$Kind-$stamp.err.log") -PassThru
    Write-PreviewEvent 'started' @{service=$Kind;pid=$child.Id;logPrefix="$Kind-$stamp"}
    $url = if ($Kind -eq 'api') {'http://127.0.0.1:18111/api/health/'} else {'http://127.0.0.1:18110/login'}
    Wait-PreviewHttp $url $child
    return $child
}
function Save-PreviewState {
    @{supervisorPid=$PID;ready=$true;apiPid=$children.api.Id;webPid=$children.web.Id;api='http://127.0.0.1:18111/api';web='http://127.0.0.1:18110';mode='offline existing fixture; independent supervisor';updatedAt=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
}
try {
    $children = @{}
    $children.api = Start-PreviewChild 'api'
    $children.web = Start-PreviewChild 'web'
    Save-PreviewState
    $restarts = @{api=0;web=0}
    while ($true) {
        Start-Sleep -Seconds 5
        foreach ($kind in @('api','web')) {
            $children[$kind].Refresh()
            if ($children[$kind].HasExited) {
                Write-PreviewEvent 'exited' @{service=$kind;pid=$children[$kind].Id;exitCode=$children[$kind].ExitCode}
                if ($restarts[$kind] -ge 3) { throw "$kind exceeded three recovery attempts; inspect logs." }
                $restarts[$kind]++
                $children[$kind] = Start-PreviewChild $kind
                Save-PreviewState
            }
        }
    }
} catch {
    Write-PreviewEvent 'supervisor-error' $_.Exception.Message
    throw
}
