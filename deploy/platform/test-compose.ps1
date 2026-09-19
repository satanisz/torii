# SPEC-0002 AC-02/03/08 static topology assertions; never starts services.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$RunId)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-ToriiProcessEnvironment
$instance = Get-ToriiInstance test $RunId 9443
$localPath = Get-ToriiLocalPath $PSScriptRoot $instance.Instance
$envPath = Join-Path $localPath '.env'
$base = Join-Path $PSScriptRoot 'compose.dev.yaml'
$overlay = Join-Path $PSScriptRoot 'compose.test.yaml'
$json = docker compose --project-directory $PSScriptRoot --env-file $envPath --project-name $instance.Project --file $base --file $overlay config --format json
if ($LASTEXITCODE -ne 0) { throw 'Compose cannot render isolated test config.' }
$config = $json | ConvertFrom-Json
$passed = 0
if ($config.name -ne $instance.Project) { throw 'Project name drift.' }; $passed++
foreach ($property in $config.services.PSObject.Properties) {
    $service = $property.Value
    if ($service.labels.'io.torii.scope' -ne 'platform' -or $service.labels.'io.torii.instance' -ne $instance.Instance) { throw 'Missing ownership label.' }
    if ($property.Name -ne 'gateway' -and $service.PSObject.Properties.Name -contains 'ports') { throw 'Private service publishes a port.' }
    if ($property.Name -ne 'gateway' -and $service.networks.PSObject.Properties.Name -contains 'ingress') { throw 'Private service joined ingress.' }
    if ($service.PSObject.Properties.Name -contains 'volumes') {
        foreach ($volume in $service.volumes) {
            if ($volume.source -match 'docker.sock|legacy|frameml|backups|scaffold') { throw 'Foreign resource in volume mount.' }
        }
    }
    if ($service.PSObject.Properties.Name -contains 'tmpfs') {
        foreach ($mount in $service.tmpfs) {
            if ($mount -notmatch '^/tmp:size=(32|64)m,mode=1777$') { throw 'Unexpected tmpfs mount or incorrectly parsed YAML options.' }
        }
    }
    if ($service.image -notmatch '@sha256:[0-9a-f]{64}$' -and $service.image -notlike "$($instance.Project)-*:local") { throw 'Image is not pinned or locally built.' }
    $passed++
}
if ($config.services.gateway.ports.Count -ne 1 -or $config.services.gateway.ports[0].host_ip -ne '127.0.0.1') { throw 'Gateway must bind only loopback.' }; $passed++
foreach ($property in $config.volumes.PSObject.Properties) {
    if ($property.Value.name -notlike "$($instance.Project)_*") { throw 'Volume outside current project.' }
    if ($property.Value.PSObject.Properties.Name -contains 'external') { throw 'External volumes are forbidden.' }
    $passed++
}
foreach ($property in $config.networks.PSObject.Properties) {
    if ($property.Value.name -notlike "$($instance.Project)_*") { throw 'Network is not dedicated.' }
    if ($property.Name -ne 'ingress' -and -not $property.Value.internal) { throw 'Application/data network is not private.' }
    $passed++
}
foreach ($property in $config.secrets.PSObject.Properties) {
    $secretPath = [IO.Path]::GetFullPath($property.Value.file)
    if ([IO.Path]::GetDirectoryName($secretPath) -ne (Join-Path $localPath 'secrets')) { throw 'Secret escaped instance directory.' }
    if (-not (Test-Path -LiteralPath $secretPath)) { throw 'Missing provisioned secret.' }
    $passed++
}
if ($config.services.api.environment.TORII_DATABASE_URL_FILE -eq $config.services.migrate.environment.TORII_DATABASE_URL_FILE) { throw 'Runtime shares migration credentials.' }; $passed++
if ($config.services.api.secrets.source -contains 'database_migrator_url') { throw 'Migrator credential exposed to API.' }; $passed++
Write-Host "$passed Compose topology checks PASS. Configuration content and credentials were not printed."
