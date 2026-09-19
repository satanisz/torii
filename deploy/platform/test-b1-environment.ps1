# Pure B1 guard tests: local Docker CLI is never invoked.
. (Join-Path $PSScriptRoot 'b1-environment.ps1')
$ErrorActionPreference = 'Stop'
$passed = 0
foreach ($name in @('PGHOSTADDR', 'PGSSLMODE', 'pgservice', 'Pg', 'DOCKER_HOST', 'docker_host')) {
    foreach ($value in @('', 'SYNTHETIC_SENSITIVE_VALUE')) {
        $environment = @{}; $environment[$name] = $value
        $rejected = $false
        try { Assert-B1AmbientEnvironment $environment } catch {
            $rejected = $true
            if ($_.Exception.Message.Contains($name) -or $_.Exception.Message.Contains('SYNTHETIC_SENSITIVE_VALUE')) { throw 'Guard reflected an environment input.' }
        }
        if (-not $rejected) { throw 'Ambient override not rejected.' }; $passed++
    }
}
foreach ($endpoint in @('npipe:////./pipe/dockerDesktopLinuxEngine', 'unix:///var/run/docker.sock')) {
    Assert-B1LocalEndpoint $endpoint; $passed++
}
foreach ($endpoint in @('tcp://127.0.0.1:2375', 'ssh://remote.invalid', 'npipe:////remote/pipe/docker', 'unix://remote/run/docker.sock', 'unix:////remote/run/docker.sock', '')) {
    $rejected = $false
    try { Assert-B1LocalEndpoint $endpoint } catch { $rejected = $true }
    if (-not $rejected) { throw 'Remote/ambiguous endpoint not rejected.' }; $passed++
}
Write-Host "$passed pure B1 environment/endpoint guard checks PASS; no Docker or network calls."
