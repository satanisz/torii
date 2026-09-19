# SPEC-0018 D07: explicit localhost-only concept demo; never reads root .env/Compose.
[CmdletBinding()]
param([ValidateSet('Start', 'Stop', 'Status')][string]$Action = 'Start')
$ErrorActionPreference = 'Stop'
$toriiRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$toriiDemo = Join-Path $toriiRoot 'apps/demo'
$toriiLocal = Join-Path $toriiDemo '.local'
$toriiPython = Join-Path $toriiDemo '.venv/Scripts/python.exe'
$toriiPidFile = Join-Path $toriiLocal 'process.json'
$toriiUrl = 'http://127.0.0.1:18440'

function Get-DemoState {
    try { return Invoke-RestMethod "$toriiUrl/demo-api/state" -TimeoutSec 2 }
    catch { return $null }
}

function Record-DemoListener {
    # Track the Windows venv redirector's server child even when HTTP readiness fails.
    $toriiListener = @(Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 18440 -ErrorAction SilentlyContinue)
    if ($toriiListener.Count -eq 0) { return $false }
    if ($toriiListener.Count -ne 1) { throw 'Unexpected demo listener ownership.' }
    $toriiServer = Get-CimInstance Win32_Process -Filter "ProcessId=$($toriiListener[0].OwningProcess)"
    if (-not $toriiServer -or
        ($toriiServer.ProcessId -ne $toriiProc.Id -and $toriiServer.ParentProcessId -ne $toriiProc.Id) -or
        $toriiServer.CommandLine -notmatch '-m torii_demo --local-demo' -or
        -not $toriiServer.CommandLine.Contains($toriiData)) { throw 'Demo listener not owned by launched process.' }
    @{ pid = $toriiServer.ProcessId; executable = $toriiServer.ExecutablePath; created = $toriiServer.CreationDate.ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $toriiPidFile
    return $true
}

if ($Action -eq 'Status') {
    $toriiState = Get-DemoState
    if ($toriiState.mode -eq 'local-demo') { Write-Host "Torii DEMO: $toriiUrl" }
    else { Write-Host 'Torii demo is not responding.' }
    return
}
if ($Action -eq 'Stop') {
    $toriiState = Get-DemoState
    if ($toriiState.runs | Where-Object { $_.status -in @('queued', 'running') }) {
        throw 'Demo training is still active. Wait for the run to finish before stopping.'
    }
    if (-not (Test-Path -LiteralPath $toriiPidFile)) { throw 'No owned demo process record.' }
    $toriiRecord = Get-Content -LiteralPath $toriiPidFile -Raw | ConvertFrom-Json
    $toriiProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$toriiRecord.pid)"
    if (-not $toriiProcess) { Write-Host 'Recorded demo process is already stopped; data retained.'; return }
    if ($toriiProcess.ExecutablePath -ne $toriiRecord.executable -or
        $toriiProcess.CommandLine -notmatch '-m torii_demo --local-demo' -or
        -not $toriiProcess.CommandLine.Contains((Join-Path $toriiLocal 'data')) -or
        $toriiProcess.CreationDate.ToUniversalTime().Ticks -ne ([datetime]$toriiRecord.created).ToUniversalTime().Ticks) {
        throw 'Refusing to stop: process ownership does not match.'
    }
    Stop-Process -Id ([int]$toriiRecord.pid)
    Write-Host 'Owned demo process stopped. All demo data retained; active run may need retry.'
    return
}
if ((Get-DemoState).mode -eq 'local-demo') { Write-Host "Torii DEMO already available: $toriiUrl"; return }
if (Get-NetTCPConnection -State Listen -LocalPort 18440 -ErrorAction SilentlyContinue) {
    throw 'Port18440 is occupied. No existing process was changed.'
}
Push-Location $toriiDemo
try { & uv sync --frozen; if ($LASTEXITCODE -ne 0) { throw 'Demo dependencies failed.' } }
finally { Pop-Location }
Push-Location (Join-Path $toriiRoot 'apps/web')
try {
    if (-not (Test-Path node_modules)) { & npm ci --ignore-scripts; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependencies failed.' } }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
New-Item -ItemType Directory -Force -Path $toriiLocal | Out-Null
$toriiData = Join-Path $toriiLocal 'data'
$toriiProc = Start-Process -FilePath $toriiPython -ArgumentList @('-m', 'torii_demo', '--local-demo', '--data-dir', "`"$toriiData`"") -WorkingDirectory $toriiDemo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $toriiLocal 'stdout.log') -RedirectStandardError (Join-Path $toriiLocal 'stderr.log')
$toriiOwned = Get-CimInstance Win32_Process -Filter "ProcessId=$($toriiProc.Id)"
@{ pid = $toriiProc.Id; executable = $toriiOwned.ExecutablePath; created = $toriiOwned.CreationDate.ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $toriiPidFile
for ($toriiAttempt = 0; $toriiAttempt -lt 30; $toriiAttempt++) {
    $toriiListenerRecorded = Record-DemoListener
    if ((Get-DemoState).mode -eq 'local-demo') {
        if (-not $toriiListenerRecorded -and -not (Record-DemoListener)) { throw 'Ready demo has no owned listener.' }
        Write-Host "Torii DEMO ready: $toriiUrl (local only, no SSO)."
        return
    }
    if ($toriiProc.HasExited) { throw 'Demo process exited. Inspect apps/demo/.local/stderr.log.' }
    Start-Sleep -Milliseconds 500
}
[void](Record-DemoListener)
throw 'Demo did not become ready; inspect apps/demo/.local/stderr.log. No other service was changed.'
