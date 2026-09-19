# SPEC-0002 partial negative tests. Own ephemeral container/network only, no stack dependency.
[CmdletBinding()]
param([ValidateRange(1024, 65535)][int]$Port = 29443, [switch]$InternalNetwork)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-ToriiFreePort $Port
$runId = (New-ToriiSecret).Substring(0, 12)
$name = "torii-gateway-check-$runId"
$localPath = Get-ToriiLocalPath $PSScriptRoot "test-$runId"
$null = New-Item -ItemType Directory -Path $localPath
$marker = "TORII_SYNTHETIC_SECRET_$runId"
$createdNetwork = $false
$createdContainer = $false
$createdUpstream = $false
try {
    & docker build --quiet --file (Join-Path $PSScriptRoot 'gateway.Dockerfile') --tag torii-platform-check-gateway:local $PSScriptRoot | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Gateway test image build failed.' }
    $networkArgs = @('network', 'create', '--label', 'io.torii.scope=platform', '--label', "io.torii.instance=test-$runId")
    if ($InternalNetwork) { $networkArgs += '--internal' }
    & docker @networkArgs $name | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated gateway-check network.' }
    $createdNetwork = $true
    & docker run --detach --name $name --network $name --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 128m --cpus 0.25 --label io.torii.scope=platform --label "io.torii.instance=test-$runId" --tmpfs /data:uid=10001,gid=10001 --tmpfs /config:uid=10001,gid=10001 --tmpfs /tmp --env "TORII_HTTPS_PORT=$Port" --publish "127.0.0.1:${Port}:9443" torii-platform-check-gateway:local | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot start isolated gateway check.' }
    $createdContainer = $true
    docker inspect --format 'Published ports: {{json .NetworkSettings.Ports}}' $name
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        # Test for the public CA, never export the private CA key.
        & docker exec $name test -f /data/caddy/pki/authorities/local/root.crt 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Gateway did not create its local CA.' }
    $caPath = Join-Path $localPath 'root-ca.crt'
    $caContent = & docker exec $name cat /data/caddy/pki/authorities/local/root.crt
    if ($LASTEXITCODE -ne 0) { throw 'CA export failed.' }
    Write-ToriiPrivateFile $caPath (($caContent -join "`n") + "`n")
    & python (Join-Path $PSScriptRoot 'check_gateway.py') --port $Port --ca $caPath --marker $marker
    if ($LASTEXITCODE -ne 0) { throw 'Gateway HTTP negative checks failed.' }
    $logs = (& docker logs $name 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read test gateway logs.' }
    if ($logs.Contains($marker)) { throw 'Synthetic secret leaked into gateway logs.' }
    Write-Host 'Gateway error-log redaction PASS. Synthetic marker absent.'
    $fixturePath = Join-Path $PSScriptRoot 'gateway_test_upstream.py'
    & docker run --detach --name "$name-upstream" --network $name --network-alias api --read-only --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges --pids-limit 32 --memory 128m --cpus 0.25 --label io.torii.scope=platform --label "io.torii.instance=test-$runId" --mount "type=bind,source=$fixturePath,target=/fixture.py,readonly" python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea python /fixture.py | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot start synthetic upstream fixture.' }
    $createdUpstream = $true
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        & docker exec "$name-upstream" python -c "import socket; socket.create_connection(('127.0.0.1',8000),timeout=1).close()" 2>$null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 250
    }
    & python (Join-Path $PSScriptRoot 'check_gateway.py') --port $Port --ca $caPath --marker $marker --upstream
    if ($LASTEXITCODE -ne 0) { throw 'Gateway fixture boundary/preservation tests failed.' }
} catch {
    if ($createdContainer) {
        $failureLog = (& docker logs $name 2>&1 | Out-String).Replace($marker, '[REDACTED]')
        Write-Host $failureLog
    }
    throw
} finally {
    if ($createdUpstream) {
        $owned = docker inspect --format '{{ index .Config.Labels "io.torii.instance" }}' "$name-upstream"
        if ($LASTEXITCODE -ne 0 -or $owned -ne "test-$runId") { throw 'Refusing cleanup of unverified fixture container.' }
        docker rm --force "$name-upstream" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Fixture container cleanup failed.' }
    }
    if ($createdContainer) {
        $owned = docker inspect --format '{{ index .Config.Labels "io.torii.instance" }}' $name
        if ($LASTEXITCODE -ne 0 -or $owned -ne "test-$runId") { throw 'Refusing cleanup of unverified gateway-check container.' }
        docker rm --force $name | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Gateway-check container cleanup failed.' }
    }
    if ($createdNetwork) {
        $owned = docker network inspect --format '{{ index .Labels "io.torii.instance" }}' $name
        if ($LASTEXITCODE -ne 0 -or $owned -ne "test-$runId") { throw 'Refusing cleanup of unverified gateway-check network.' }
        docker network rm $name | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Gateway-check network cleanup failed.' }
    }
    Write-Host 'Ephemeral gateway resources removed; only public CA remains in ignored .local test directory.'
}
