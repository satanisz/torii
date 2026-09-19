# SPEC-0002 AC-02/03/08. Generates new local-only state, never rotates in place.
[CmdletBinding()]
param(
    [ValidateSet('dev', 'test')][string]$Profile = 'dev',
    [string]$RunId,
    [ValidateRange(1024, 65535)][int]$Port = 9443,
    [switch]$FixtureUsers
)
. (Join-Path $PSScriptRoot 'common.ps1')
if ($Profile -eq 'test' -and -not $RunId) {
    $RunId = (New-ToriiSecret).Substring(0, 12)
}
$instance = Get-ToriiInstance $Profile $RunId $Port
$localPath = Get-ToriiLocalPath $PSScriptRoot $instance.Instance
if (Test-Path -LiteralPath $localPath) {
    throw 'Instance already exists. Provisioning never overwrites passwords or persisted realm identity.'
}
Assert-ToriiFreePort $Port
$null = New-Item -ItemType Directory -Path (Join-Path $localPath 'secrets')
# Restrict generated secrets at the directory boundary before writing them.
if ($env:OS -eq 'Windows_NT') {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = Get-Acl -LiteralPath $localPath
    $acl.SetAccessRuleProtection($true, $false)
    $rule = [Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $localPath -AclObject $acl
} else {
    & chmod 700 $localPath (Join-Path $localPath 'secrets')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict local credentials directory.' }
}
$secrets = @{}
foreach ($name in @('postgres_admin', 'postgres_migrator', 'postgres_runtime', 'postgres_identity', 'identity_admin', 'oidc_client_secret', 'cursor_key')) {
    $secrets[$name] = New-ToriiSecret
}
$secrets['session_key'] = [Convert]::ToBase64String((New-ToriiRandomBytes)).Replace('+', '-').Replace('/', '_')
$secrets['database_migrator_url'] = "postgresql+psycopg://torii_migrator:$($secrets.postgres_migrator)@database:5432/torii_platform"
$secrets['database_runtime_url'] = "postgresql+psycopg://torii_runtime:$($secrets.postgres_runtime)@database:5432/torii_platform"
foreach ($name in $secrets.Keys) {
    Write-ToriiPrivateFile (Join-Path $localPath "secrets/$name") $secrets[$name]
}
$publicUrl = "https://localhost:$Port"
$realm = @{
    realm = 'torii-dev'; enabled = $true; sslRequired = 'external'
    registrationAllowed = $false; resetPasswordAllowed = $false
    loginWithEmailAllowed = $false; duplicateEmailsAllowed = $false
    bruteForceProtected = $true; accessTokenLifespan = 300
    ssoSessionIdleTimeout = 1800; ssoSessionMaxLifespan = 28800
    clients = @(@{
        clientId = 'torii-web'; name = 'Torii local web'; enabled = $true
        protocol = 'openid-connect'; publicClient = $false
        secret = $secrets.oidc_client_secret; standardFlowEnabled = $true
        directAccessGrantsEnabled = $false; serviceAccountsEnabled = $false
        implicitFlowEnabled = $false
        redirectUris = @("$publicUrl/auth/callback"); webOrigins = @($publicUrl)
        attributes = @{ 'pkce.code.challenge.method' = 'S256' }
        protocolMappers = @(@{
            name = 'torii-api-audience'; protocol = 'openid-connect'
            protocolMapper = 'oidc-audience-mapper'; consentRequired = $false
            config = @{
                'included.custom.audience' = 'torii-api'
                'id.token.claim' = 'false'; 'access.token.claim' = 'true'
                'introspection.token.claim' = 'true'
            }
        })
    })
    users = @()
}
if ($FixtureUsers) {
    foreach ($username in @('alice', 'bob', 'eve')) {
        $password = New-ToriiSecret
        Write-ToriiPrivateFile (Join-Path $localPath "secrets/user_$username") $password
        $realm.users += @{
            username = $username; enabled = $true; emailVerified = $true
            firstName = $username; lastName = 'Synthetic fixture'
            email = "$username@example.invalid"
            credentials = @(@{ type = 'password'; value = $password; temporary = $false })
        }
    }
}
Write-ToriiPrivateFile (Join-Path $localPath 'realm.json') ($realm | ConvertTo-Json -Depth 15)
$forwardPath = $localPath.Replace('\', '/')
$envText = "TORII_COMPOSE_PROJECT=$($instance.Project)`nTORII_INSTANCE=$($instance.Instance)`nTORII_HTTPS_PORT=$Port`nTORII_LOCAL_DIR=$forwardPath`n"
Write-ToriiPrivateFile (Join-Path $localPath '.env') $envText
$metadata = @{
    instance = $instance.Instance; project = $instance.Project; port = $Port
    fixture_users = [bool]$FixtureUsers; created_at = [DateTime]::UtcNow.ToString('o')
    spec = 'SPEC-0002'; state = 'provisioned-not-started'
}
Write-ToriiPrivateFile (Join-Path $localPath 'instance.json') ($metadata | ConvertTo-Json)
Write-Host "Provisioned $($instance.Instance). No service started; no secret printed."
Write-Host "Configuration: $localPath"
Write-Host 'Passwords are local secrets; no platform grants are inferred from IdP users.'
