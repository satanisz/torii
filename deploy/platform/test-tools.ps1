# No Docker needed. SPEC-0002 AC-02/08 negative tooling tests, not full AC proof.
. (Join-Path $PSScriptRoot 'common.ps1')
$passed = 0
function Expect-Rejection {
    param([scriptblock]$Operation)
    $rejected = $false
    try { & $Operation | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw 'Expected unsafe input to be rejected.' }
    $script:passed++
}
$dev = Get-ToriiInstance dev '' 9443
if ($dev.Project -ne 'torii-platform-dev') { throw 'Dev project mismatch.' }; $passed++
$test = Get-ToriiInstance test abcdef012345 19443
if ($test.Project -ne 'torii-platform-test-abcdef012345') { throw 'Test project mismatch.' }; $passed++
Expect-Rejection { Get-ToriiInstance test '../legacy' 9443 }
Expect-Rejection { Get-ToriiInstance test '' 9443 }
Expect-Rejection { Get-ToriiInstance test ABCDEF012345 9443 }
Expect-Rejection { Get-ToriiInstance dev abcdef012345 9443 }
Expect-Rejection { Get-ToriiInstance prod '' 9443 }
Expect-Rejection { Get-ToriiInstance dev '' 443 }
Expect-Rejection { Get-ToriiLocalPath $PSScriptRoot '../legacy' }
foreach ($name in @('TORII_COMPOSE_PROJECT', 'TORII_INSTANCE', 'TORII_HTTPS_PORT', 'TORII_LOCAL_DIR')) {
    $override = @{}; $override[$name] = ''
    Expect-Rejection { Assert-ToriiProcessEnvironment $override }
}
$secret = New-ToriiSecret
if ($secret -cnotmatch '^[0-9a-f]{64}$') { throw 'Secret format mismatch.' }; $passed++
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
try {
    $listener.Start()
    $testPort = $listener.LocalEndpoint.Port
    Expect-Rejection { Assert-ToriiFreePort $testPort }
} finally { $listener.Stop() }
Write-Host "$passed tooling checks PASS. No containers created or changed."
