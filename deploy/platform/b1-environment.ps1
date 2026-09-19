# SPEC-0001 B1 exact-target guard. Pure checks never echo input names or values.
function Assert-B1AmbientEnvironment {
    param([System.Collections.IDictionary]$Values = [Environment]::GetEnvironmentVariables())
    foreach ($key in $Values.Keys) {
        if ([string]$key -imatch '^PG' -or [string]$key -ieq 'DOCKER_HOST') {
            throw 'Inherited database or Docker endpoint environment is forbidden for B1 tests.'
        }
    }
}

function Assert-B1LocalEndpoint {
    param([string]$Endpoint)
    if ($Endpoint -cnotmatch '^npipe:/{2,4}\./pipe/[A-Za-z0-9_.-]+$' -and $Endpoint -cnotmatch '^unix:///(?!/)[^\x00\r\n?#]+$') {
        throw 'B1 tests require a local Docker named pipe or Unix socket.'
    }
}

function Get-B1DockerContext {
    Assert-B1AmbientEnvironment
    $context = (& docker context show 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $context -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$') {
        throw 'Cannot resolve a valid local Docker context for B1 tests.'
    }
    $endpointJson = (& docker context inspect $context --format '{{json .Endpoints.docker.Host}}' 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect local Docker context for B1 tests.' }
    try { $endpoint = $endpointJson | ConvertFrom-Json } catch { throw 'Invalid Docker endpoint configuration for B1 tests.' }
    Assert-B1LocalEndpoint $endpoint
    return $context
}
