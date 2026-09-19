# SPEC-0001 B1: dedicated temporary PostgreSQL, never an existing platform/legacy DB.
[CmdletBinding()]
param([string[]]$TestArgs = @('tests/integration'))
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot 'b1-environment.ps1')
Assert-B1AmbientEnvironment
$ErrorActionPreference = 'Stop'
$apiRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../apps/api'))
$image = 'postgres:17@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675'
$runId = [Guid]::NewGuid().ToString('N')
$name = "torii-b1-$runId"
$envNames = @('TORII_B1_RUN_ID', 'TORII_B1_CONTAINER_ID', 'TORII_B1_PORT', 'TORII_B1_DOCKER_CONTEXT', 'TORII_B1_ADMIN_PASSWORD', 'TORII_B1_MIGRATOR_PASSWORD', 'TORII_B1_RUNTIME_PASSWORD')
foreach ($key in $envNames) {
    if ([Environment]::GetEnvironmentVariables().Contains($key)) { throw 'Existing TORII_B1_* environment refused; start a fresh harness process.' }
}
foreach ($argument in $TestArgs) {
    if ($argument -eq '-l' -or $argument -match 'showlocals' -or $argument -in @('-o', '--override-ini', '-c', '--config-file') -or $argument.StartsWith('-o') -or $argument.StartsWith('-c') -or $argument.StartsWith('--override-ini') -or $argument.StartsWith('--config-file')) {
        throw 'TestArgs must not enable locals/config overrides that may print credentials.'
    }
}
if (-not $TestArgs.Count) { throw 'At least one test selection argument is required.' }
$previousEnvironment = @{}
foreach ($key in ($envNames + @('POSTGRES_PASSWORD', 'PYTEST_ADDOPTS', 'DOCKER_CONTEXT'))) {
    $previousEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
$containerId = $null
$networkId = $null
$testExitCode = 1
$dockerContext = Get-B1DockerContext
try {
    $env:DOCKER_CONTEXT = $dockerContext
    $env:TORII_B1_DOCKER_CONTEXT = $dockerContext
    Assert-ToriiDocker
    & uv sync --project $apiRoot --frozen | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen API test toolchain installation failed.' }
    $env:TORII_B1_RUN_ID = $runId
    $env:TORII_B1_ADMIN_PASSWORD = New-ToriiSecret
    $env:TORII_B1_MIGRATOR_PASSWORD = New-ToriiSecret
    $env:TORII_B1_RUNTIME_PASSWORD = New-ToriiSecret
    $env:POSTGRES_PASSWORD = $env:TORII_B1_ADMIN_PASSWORD
    $env:PYTEST_ADDOPTS = ''
    $networkId = (& docker --context $dockerContext network create --label io.torii.scope=b1-integration --label "io.torii.test-run=$runId" $name 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $networkId -notmatch '^[0-9a-f]{64}$') { throw 'B1 network creation failed.' }
    $containerId = (& docker --context $dockerContext run --detach --name $name --network $networkId --label io.torii.scope=b1-integration --label "io.torii.test-run=$runId" --env POSTGRES_PASSWORD --env 'POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=peer' --env PGDATA=/var/lib/postgresql/data/pgdata --tmpfs /var/lib/postgresql/data:rw,size=768m --publish 127.0.0.1::5432 --pids-limit 128 --memory 1g --cpus 1 --security-opt no-new-privileges $image 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $containerId -notmatch '^[0-9a-f]{64}$') { throw 'B1 PostgreSQL container creation failed.' }
    $env:TORII_B1_CONTAINER_ID = $containerId
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & docker --context $dockerContext exec --user postgres $containerId pg_isready -h 127.0.0.1 -U postgres -d postgres *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'B1 PostgreSQL did not become ready. Raw logs are withheld to protect secrets.' }
    $binding = (& docker --context $dockerContext inspect --format '{{json (index .NetworkSettings.Ports "5432/tcp")}}' $containerId | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or $binding.Count -ne 1 -or $binding[0].HostIp -ne '127.0.0.1') { throw 'B1 PostgreSQL must publish only one loopback port.' }
    $env:TORII_B1_PORT = $binding[0].HostPort
    # Random validated hex prevents SQL quoting; bootstrap output is never emitted.
    $bootstrap = @"
CREATE ROLE torii_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '$($env:TORII_B1_MIGRATOR_PASSWORD)';
CREATE ROLE torii_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '$($env:TORII_B1_RUNTIME_PASSWORD)';
"@
    $bootstrap | & docker --context $dockerContext exec --interactive --user postgres $containerId psql -U postgres -d postgres --set ON_ERROR_STOP=1 --quiet *> $null
    if ($LASTEXITCODE -ne 0) { throw 'B1 role bootstrap failed; raw SQL diagnostics withheld.' }
    Write-Host "B1 run ${runId}: new PostgreSQL at loopback ephemeral port, separate roles, tmpfs only."
    Push-Location $apiRoot
    try {
        & uv run --frozen --no-sync pytest -c (Join-Path $apiRoot 'pyproject.toml') -m integration --tb=short @TestArgs --no-showlocals
        $testExitCode = $LASTEXITCODE
    } finally { Pop-Location }
} finally {
    try {
        if ($containerId -and $containerId -match '^[0-9a-f]{64}$') {
            $ownership = (& docker --context $dockerContext inspect --format '{{.Id}}|{{index .Config.Labels "io.torii.scope"}}|{{index .Config.Labels "io.torii.test-run"}}' $containerId 2>$null | Out-String).Trim()
            if ($LASTEXITCODE -ne 0 -or $ownership -ne "$containerId|b1-integration|$runId") { throw 'B1 container cleanup refused: exact ID/labels mismatch.' }
            & docker --context $dockerContext rm --force $containerId *> $null
            if ($LASTEXITCODE -ne 0) { throw 'B1 container cleanup failed.' }
        }
        if ($networkId -and $networkId -match '^[0-9a-f]{64}$') {
            $ownership = (& docker --context $dockerContext network inspect --format '{{.Id}}|{{index .Labels "io.torii.scope"}}|{{index .Labels "io.torii.test-run"}}' $networkId 2>$null | Out-String).Trim()
            if ($LASTEXITCODE -ne 0 -or $ownership -ne "$networkId|b1-integration|$runId") { throw 'B1 network cleanup refused: exact ID/labels mismatch.' }
            & docker --context $dockerContext network rm $networkId *> $null
            if ($LASTEXITCODE -ne 0) { throw 'B1 network cleanup failed.' }
        }
        Write-Host "B1 run ${runId}: verified temporary container/network removed; tmpfs test data discarded."
    } finally {
        foreach ($key in $previousEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previousEnvironment[$key], 'Process')
        }
    }
}
if ($testExitCode -ne 0) { throw "B1 integration tests failed (pytest exit $testExitCode)." }
