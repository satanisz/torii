# SPEC-0002. Pure validation helpers shared by lifecycle tooling and tests.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-ToriiProcessEnvironment {
    param([System.Collections.IDictionary]$Values = [Environment]::GetEnvironmentVariables())
    foreach ($name in @('TORII_COMPOSE_PROJECT', 'TORII_INSTANCE', 'TORII_HTTPS_PORT', 'TORII_LOCAL_DIR')) {
        if ($Values.Contains($name)) {
            throw "Remove process environment variable $name before running isolated Compose tooling; process env overrides --env-file."
        }
    }
}

function Get-ToriiInstance {
    param([string]$Profile, [string]$RunId, [int]$Port)
    if ($Profile -notin @('dev', 'test')) { throw 'Profile must be dev or test.' }
    if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be 1024..65535.' }
    if ($Profile -eq 'dev') {
        if ($RunId) { throw 'Dev does not accept a run ID.' }
        $instance = 'dev'
    } else {
        if ($RunId -cnotmatch '^[0-9a-f]{12}$') { throw 'Test run ID must be 12 lowercase hexadecimal characters.' }
        $instance = "test-$RunId"
    }
    return [pscustomobject]@{
        Instance = $instance
        Project = "torii-platform-$instance"
        Port = $Port
    }
}

function Get-ToriiLocalPath {
    param([string]$BasePath, [string]$Instance)
    if ($Instance -cnotmatch '^(dev|test-[0-9a-f]{12})$') { throw 'Invalid local instance.' }
    $localRoot = [IO.Path]::GetFullPath((Join-Path $BasePath '.local'))
    $target = [IO.Path]::GetFullPath((Join-Path $localRoot $Instance))
    if ([IO.Path]::GetDirectoryName($target) -ne $localRoot) { throw 'Path escapes local directory.' }
    return $target
}

function Assert-ToriiFreePort {
    param([int]$Port)
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    $listener.Server.ExclusiveAddressUse = $true
    try { $listener.Start() } catch { throw "Loopback port $Port is occupied. No existing service was stopped." }
    finally { $listener.Stop() }
}

function New-ToriiRandomBytes {
    param([int]$Count = 32)
    $buffer = New-Object byte[] $Count
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return ,$buffer
}

function New-ToriiSecret {
    return [BitConverter]::ToString((New-ToriiRandomBytes)).Replace('-', '').ToLowerInvariant()
}

function Write-ToriiPrivateFile {
    param([string]$Path, [string]$Content)
    if (Test-Path -LiteralPath $Path) { throw "Refusing to overwrite existing provisioned file: $Path" }
    [IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
}

function Assert-ToriiDocker {
    $summary = docker info --format '{{json .}}' 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or -not $summary) { throw 'Docker Desktop Linux engine is unavailable.' }
    if ($summary.OSType -ne 'linux') { throw 'Linux Docker containers are required.' }
    if ($summary.NCPU -lt 4 -or $summary.MemTotal -lt 8GB) { throw 'Docker requires at least 4 CPU and 8 GiB for D1.' }
    $usage = @(docker stats --no-stream --format '{{.MemUsage}}')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot measure current Docker memory use.' }
    $usedBytes = 0.0
    foreach ($line in $usage) {
        if (-not $line) { continue }
        $first = ($line -split '/')[0].Trim()
        if ($first -notmatch '^([0-9.]+)(B|KiB|MiB|GiB|TiB)$') { throw 'Unrecognized Docker memory measurement.' }
        $number = [double]::Parse($Matches[1], [Globalization.CultureInfo]::InvariantCulture)
        $factor = switch ($Matches[2]) { B { 1 }; KiB { 1KB }; MiB { 1MB }; GiB { 1GB }; TiB { 1TB } }
        $usedBytes += $number * $factor
    }
    $estimatedHeadroom = $summary.MemTotal - $usedBytes - 1GB
    if ($estimatedHeadroom -lt 8GB) { throw 'Estimated Docker headroom below 8 GiB (+1 GiB engine reserve). Existing services were not changed.' }
    Write-Host ('Docker: {0} CPU, {1:N1} GiB total, estimated headroom {2:N1} GiB after 1 GiB reserve.' -f $summary.NCPU, ($summary.MemTotal / 1GB), ($estimatedHeadroom / 1GB))
    Write-Host 'Headroom is an estimate from container working sets, not a guarantee against host memory pressure.'
}
