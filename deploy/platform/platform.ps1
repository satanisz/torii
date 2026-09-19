# SPEC-0002 AC-01/02/08. Always explicit files, env and Compose project.
[CmdletBinding()]
param(
    [ValidateSet('check', 'preflight', 'build', 'up', 'stop', 'status', 'export-ca', 'cleanup-test')]
    [string]$Action = 'check',
    [ValidateSet('dev', 'test')][string]$Profile = 'dev',
    [string]$RunId,
    [switch]$ConfirmTestDeletion
)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-ToriiProcessEnvironment
$instance = Get-ToriiInstance $Profile $RunId 9443
$localPath = Get-ToriiLocalPath $PSScriptRoot $instance.Instance
$metadataPath = Join-Path $localPath 'instance.json'
if (-not (Test-Path -LiteralPath $metadataPath)) { throw 'Run provision.ps1 for this instance first.' }
$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
if ($metadata.project -ne $instance.Project -or $metadata.instance -ne $instance.Instance) { throw 'Provisioned instance metadata mismatch.' }
$instance = Get-ToriiInstance $Profile $RunId $metadata.port
$expectedEnv = @{
    TORII_COMPOSE_PROJECT = $instance.Project
    TORII_INSTANCE = $instance.Instance
    TORII_HTTPS_PORT = [string]$instance.Port
    TORII_LOCAL_DIR = $localPath.Replace('\', '/')
}
$seen = @{}
foreach ($line in (Get-Content -LiteralPath (Join-Path $localPath '.env'))) {
    $parts = $line -split '=', 2
    if ($parts.Count -ne 2 -or -not $expectedEnv.ContainsKey($parts[0]) -or $seen.ContainsKey($parts[0])) { throw 'Unexpected or duplicate instance env setting.' }
    if ($expectedEnv[$parts[0]] -cne $parts[1]) { throw 'Instance env does not match the bounded provisioned path/project/port.' }
    $seen[$parts[0]] = $true
}
if ($seen.Count -ne $expectedEnv.Count) { throw 'Missing instance env setting.' }
foreach ($name in @('postgres_admin', 'postgres_migrator', 'postgres_runtime', 'postgres_identity', 'identity_admin', 'database_migrator_url', 'database_runtime_url', 'session_key', 'cursor_key', 'oidc_client_secret')) {
    $secretPath = Join-Path $localPath "secrets/$name"
    if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf) -or (Get-Item -LiteralPath $secretPath).Length -eq 0) { throw 'Required secret file is missing or empty; provision a fresh isolated instance.' }
}
$compose = @('compose', '--project-directory', $PSScriptRoot, '--env-file', (Join-Path $localPath '.env'), '--project-name', $instance.Project, '--file', (Join-Path $PSScriptRoot 'compose.dev.yaml'))
if ($Profile -eq 'test') { $compose += @('--file', (Join-Path $PSScriptRoot 'compose.test.yaml')) }

function Invoke-ToriiCompose {
    param([string[]]$Arguments)
    & docker @compose @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Compose operation failed for $($instance.Project); inspect bounded service logs locally without sharing secrets." }
}

function Assert-OwnResources {
    # Inspect every labeled resource before allowing Compose test destruction.
    $containerIds = @(docker ps -a -q --filter "label=com.docker.compose.project=$($instance.Project)")
    $volumeIds = @(docker volume ls -q --filter "label=com.docker.compose.project=$($instance.Project)")
    $networkIds = @(docker network ls -q --filter "label=com.docker.compose.project=$($instance.Project)")
    foreach ($kind in @('container', 'volume', 'network')) {
        $ids = switch ($kind) { container { $containerIds }; volume { $volumeIds }; network { $networkIds } }
        foreach ($id in $ids) {
            if (-not $id) { continue }
            $result = docker $kind inspect $id | ConvertFrom-Json
            if ($LASTEXITCODE -ne 0) { throw 'Cannot verify cleanup resource.' }
            $labels = if ($kind -eq 'container') { $result[0].Config.Labels } else { $result[0].Labels }
            if ($labels.'io.torii.scope' -ne 'platform' -or $labels.'io.torii.instance' -ne $instance.Instance) {
                throw 'Cleanup refused: resource ownership label mismatch.'
            }
        }
    }
}

switch ($Action) {
    check { Invoke-ToriiCompose @('config', '--quiet'); Write-Host 'Compose syntax and interpolation PASS (not a runtime test).' }
    preflight {
        Assert-ToriiDocker
        Assert-ToriiFreePort $instance.Port
        Invoke-ToriiCompose @('config', '--quiet')
        docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}'
        Write-Host 'Preflight PASS. Require >=8 GiB available for the new stack; no existing services changed.'
    }
    build { Invoke-ToriiCompose @('build') }
    up {
        Assert-ToriiDocker
        $runningGateway = docker ps -q --filter "label=com.docker.compose.project=$($instance.Project)" --filter 'label=com.docker.compose.service=gateway'
        if (-not $runningGateway) { Assert-ToriiFreePort $instance.Port }
        Invoke-ToriiCompose @('up', '--detach', '--wait', '--wait-timeout', '240')
    }
    stop { Invoke-ToriiCompose @('stop'); Write-Host 'Only this platform instance stopped. Volumes preserved.' }
    status { Invoke-ToriiCompose @('ps', '--all') }
    export-ca {
        $gatewayId = docker ps -q --filter "label=com.docker.compose.project=$($instance.Project)" --filter 'label=com.docker.compose.service=gateway'
        if (-not $gatewayId) { throw 'Gateway is not running.' }
        & docker cp "${gatewayId}:/data/caddy/pki/authorities/local/root.crt" (Join-Path $localPath 'root-ca.crt')
        if ($LASTEXITCODE -ne 0) { throw 'Cannot export local CA.' }
        Write-Host 'CA exported locally, NOT installed into any trust store. Use only a dedicated client/test profile.'
    }
    cleanup-test {
        if ($Profile -ne 'test' -or -not $ConfirmTestDeletion) { throw 'Cleanup requires a test run ID and -ConfirmTestDeletion.' }
        Assert-OwnResources
        Invoke-ToriiCompose @('down', '--volumes')
        Write-Host 'Removed only verified Compose resources of this test. Test DB volumes are not recoverable without a backup.'
        Write-Host 'Local secrets/CA remain ignored on disk; no filesystem recursive deletion was performed.'
    }
}
