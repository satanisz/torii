# SPEC-0002 AC-07 partial integration: canonical discovery, not complete OIDC auth.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$RunId)
. (Join-Path $PSScriptRoot 'common.ps1')
$instance = Get-ToriiInstance test $RunId 9443
$localPath = Get-ToriiLocalPath $PSScriptRoot $instance.Instance
$metadata = Get-Content -LiteralPath (Join-Path $localPath 'instance.json') -Raw | ConvertFrom-Json
$expectedIssuer = "https://localhost:$($metadata.port)/identity/realms/torii-dev"
$identityId = @(docker ps -q --filter "label=com.docker.compose.project=$($instance.Project)" --filter 'label=com.docker.compose.service=identity')
if ($LASTEXITCODE -ne 0 -or $identityId.Count -ne 1) { throw 'Expected one running identity service in this test instance.' }
$passed = 0
foreach ($headers in @('Host: localhost', 'Host: malicious.invalid\r\nX-Forwarded-Host: malicious.invalid\r\nX-Forwarded-Proto: http')) {
    $command = 'exec 3<>/dev/tcp/127.0.0.1/8080; printf "GET /identity/realms/torii-dev/.well-known/openid-configuration HTTP/1.0\r\n' + $headers + '\r\n\r\n" >&3; cat <&3'
    $response = docker exec $identityId[0] bash -c $command
    if ($LASTEXITCODE -ne 0 -or $response[0] -notmatch '^HTTP/1.0 200 ') { throw 'Discovery HTTP request failed.' }
    $json = $response | Where-Object { $_.StartsWith('{') }
    $discovery = $json | ConvertFrom-Json
    if ($discovery.issuer -cne $expectedIssuer) { throw 'Canonical issuer mismatch.' }; $passed++
    foreach ($field in @('authorization_endpoint', 'token_endpoint', 'jwks_uri', 'revocation_endpoint')) {
        if (-not $discovery.$field.StartsWith("$expectedIssuer/", [StringComparison]::Ordinal)) { throw 'Canonical public endpoint mismatch.' }
        $passed++
    }
}
Write-Host "$passed discovery checks PASS, including untrusted Host/Forwarded headers. Login/token verification not tested by this script."
