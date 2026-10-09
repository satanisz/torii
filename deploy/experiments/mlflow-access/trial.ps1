# SPEC-0020 AC-01..06. Explicit isolated Compose invocation, no legacy environment.
[CmdletBinding()]
param(
    [ValidateSet('provision', 'check', 'build', 'up', 'status', 'inspect', 'test', 'train', 'stop')]
    [string]$Action = 'status',
    [ValidatePattern('^[a-f0-9]{12}$')][string]$RunId,
    [ValidateRange(1024, 65535)][int]$Port = 18500
)
$ErrorActionPreference = 'Stop'
foreach ($name in @('TRIAL_ID','TRIAL_LOCAL','TRIAL_PORT','TRIAL_IMAGE_ID')) {
    if (Test-Path "Env:$name") { throw "Remove process override $name before using this harness." }
}
function Write-PrivateFile([string]$Path, [string]$Value) {
    [IO.File]::WriteAllText($Path, $Value, [Text.UTF8Encoding]::new($false))
}
function New-Secret {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
function Assert-FreePort([int]$Number) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Number)
    try { $listener.Start() } finally { $listener.Stop() }
}
if (-not $RunId) {
    if ($Action -ne 'provision') { throw 'Provide the RunId printed by provision.' }
    $RunId = ([guid]::NewGuid().ToString('N')).Substring(0,12)
}
$localPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".local/$RunId"))
$project = "torii-exp03-$RunId"
if ($Action -eq 'provision') {
    if (Test-Path -LiteralPath $localPath) { throw 'Instance exists. Never overwrite persisted credentials.' }
    Assert-FreePort $Port
    $null = New-Item -ItemType Directory -Path $localPath
    if ($env:OS -eq 'Windows_NT') {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $acl = Get-Acl -LiteralPath $localPath
        $acl.SetAccessRuleProtection($true, $false)
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
        Set-Acl -LiteralPath $localPath -AclObject $acl
    } else {
        & chmod 700 $localPath
        if ($LASTEXITCODE -ne 0) { throw 'Cannot restrict secrets directory.' }
    }
    $null = New-Item -ItemType Directory -Path (Join-Path $localPath 'secrets')
    $null = New-Item -ItemType Directory -Path (Join-Path $localPath 'results')
    $values = @{}
    foreach ($name in @('postgres_admin','postgres_tracking','postgres_auth','admin_password',
        'user_a','user_b','flask_key','s3_access','s3_secret')) {
        $values[$name] = New-Secret
        Write-PrivateFile (Join-Path $localPath "secrets/$name") $values[$name]
    }
    $config = @"
[mlflow]
default_permission = NO_PERMISSIONS
database_uri = postgresql+psycopg2://mlflow_auth:$($values.postgres_auth)@database:5432/mlflow_auth
admin_username = admin
admin_password = $($values.admin_password)
authorization_function = mlflow.server.auth:authenticate_request_basic_auth
grant_default_workspace_access = false
auth_cache_ttl_seconds = 0
"@
    Write-PrivateFile (Join-Path $localPath 'secrets/auth_config') $config
    $s3 = @{identities=@(@{name='mlflow';credentials=@(@{
        accessKey=$values.s3_access;secretKey=$values.s3_secret
    });actions=@('Admin','Read','Write','List','Tagging')})} | ConvertTo-Json -Depth 8
    Write-PrivateFile (Join-Path $localPath 'secrets/s3_config') $s3
    $forward = $localPath.Replace('\','/')
    Write-PrivateFile (Join-Path $localPath '.env') "TRIAL_ID=$RunId`nTRIAL_PORT=$Port`nTRIAL_LOCAL=$forward`n"
    $metadata = @{run_id=$RunId;project=$project;port=$Port;spec='SPEC-0020';created_at=[DateTime]::UtcNow.ToString('o')}
    Write-PrivateFile (Join-Path $localPath 'instance.json') ($metadata | ConvertTo-Json)
    Write-Host "Provisioned RunId=$RunId (no services started; secrets kept locally)."
    return
}
$metadata = Get-Content -LiteralPath (Join-Path $localPath 'instance.json') -Raw | ConvertFrom-Json
if ($metadata.run_id -cne $RunId -or $metadata.project -cne $project -or $metadata.spec -cne 'SPEC-0020') {
    throw 'Instance metadata mismatch.'
}
if ($metadata.port -lt 1024 -or $metadata.port -gt 65535) { throw 'Invalid persisted port.' }
$expectedEnv = "TRIAL_ID=$RunId`nTRIAL_PORT=$($metadata.port)`nTRIAL_LOCAL=$($localPath.Replace('\','/'))`n"
if ((Get-Content -LiteralPath (Join-Path $localPath '.env') -Raw) -cne $expectedEnv) { throw 'Instance environment mismatch.' }
$compose = @('compose','--project-directory',$PSScriptRoot,'--env-file',(Join-Path $localPath '.env'),
    '--project-name',$project,'--file',(Join-Path $PSScriptRoot 'compose.yaml'),'--profile','tools')
function Invoke-Compose([string[]]$Arguments) {
    & docker @compose @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Compose failed for $project (exit $LASTEXITCODE)." }
}
function Set-ImageIdentity {
    $id = & docker image inspect "torii-exp03-${RunId}:local" --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $id -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Build the trial image first.' }
    $env:TRIAL_IMAGE_ID = $id
}
function Invoke-Report([string]$Service, [string]$Prefix, [string]$Name, [string[]]$Extra = @()) {
    $output = @(& docker @compose run --rm --no-deps -T $Service @Extra)
    $exitCode = $LASTEXITCODE
    $line = @($output | Where-Object { $_.StartsWith($Prefix) })
    if ($line.Count -ne 1) { throw "Missing safe report from $Service (exit $exitCode)." }
    $json = $line[0].Substring($Prefix.Length)
    $result = $json | ConvertFrom-Json
    Write-PrivateFile (Join-Path $localPath "results/$Name.json") $json
    Write-Host "$Name report saved (exit $exitCode)."
    if ($exitCode -ne 0) { throw "$Name failed; see its sanitized report." }
    return $result
}
function Verify-Persisted {
    $inputJson = Get-Content -LiteralPath (Join-Path $localPath 'results/train-1.json') -Raw
    $output = @($inputJson | & docker @compose run --rm --no-deps -T verify)
    $exitCode = $LASTEXITCODE
    $line = @($output | Where-Object { $_.StartsWith('TORII_VERIFY_RESULT=') })
    if ($line.Count -ne 1 -or $exitCode -ne 0) { throw 'Persistence verification failed.' }
    Write-PrivateFile (Join-Path $localPath 'results/persistence.json') $line[0].Substring('TORII_VERIFY_RESULT='.Length)
}
function Inspect-Isolation {
    $json = & docker @compose config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect resolved configuration.' }
    $cfg = $json | ConvertFrom-Json
    foreach ($job in @('train','verify','bootstrap','access-check')) {
        $service = $cfg.services.$job
        if (-not $service.read_only -or $service.volumes -or $service.ports -or $service.privileged) { throw 'Unsafe job configuration.' }
        $networkNames = @($service.networks.PSObject.Properties.Name)
        if ($networkNames.Count -ne 1 -or $networkNames[0] -ne 'api') { throw 'Job has unexpected network access.' }
    }
    foreach ($job in @('train','verify')) {
        $names = @($cfg.services.$job.secrets | ForEach-Object { $_.source })
        if ($names.Count -ne 1 -or $names[0] -ne 'user_a') { throw 'Worker has excess credentials.' }
    }
    if ($cfg.services.database.ports -or $cfg.services.storage.ports -or $cfg.services.mlflow.ports) { throw 'Backend port is published.' }
    if (@($cfg.services.gateway.ports).Count -ne 1 -or $cfg.services.gateway.ports[0].host_ip -ne '127.0.0.1') { throw 'Gateway port is not loopback-only.' }
    if ($cfg.services.gateway.secrets -or $cfg.services.gateway.volumes) { throw 'Gateway has unexpected credentials or data.' }
    foreach ($network in @('api','backend')) {
        if (-not $cfg.networks.$network.internal) { throw 'Runtime network allows external egress.' }
    }
    $cpu = 0.0; $memory = [long]0
    foreach ($service in @('database','storage','mlflow','gateway','train')) {
        $cpu += [double]$cfg.services.$service.cpus
        $memory += [long]$cfg.services.$service.mem_limit
    }
    if ($cpu -gt 4 -or $memory -gt 4GB) { throw 'Combined resource budget exceeded.' }
    $ids = @(& docker ps -q --filter "label=com.docker.compose.project=$project")
    if ($LASTEXITCODE -ne 0 -or $ids.Count -ne 4) { throw 'Expected exactly four running trial services.' }
    $safe = @()
    foreach ($id in $ids) {
        $raw = & docker inspect $id
        if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed.' }
        $item = @($raw | ConvertFrom-Json)[0]
        if ($item.Config.Labels.'io.torii.scope' -ne 'exp03' -or $item.Config.Labels.'io.torii.instance' -ne $RunId) { throw 'Unexpected resource ownership.' }
        foreach ($mount in $item.Mounts) {
            if ($mount.Type -eq 'bind' -and ($mount.Destination -notlike '/run/secrets/*' -or $mount.RW)) { throw 'Unexpected host bind mount.' }
            if ($mount.Type -eq 'volume' -and $mount.Name -notlike "${project}_*") { throw 'Foreign volume mounted.' }
        }
        if ($item.HostConfig.Privileged -or $item.HostConfig.NetworkMode -eq 'host') { throw 'Unsafe runtime privileges.' }
        $safe += @{
            name=$item.Name;image_id=$item.Image;service=$item.Config.Labels.'com.docker.compose.service'
            memory_limit=$item.HostConfig.Memory;nano_cpus=$item.HostConfig.NanoCpus
            networks=@($item.NetworkSettings.Networks.PSObject.Properties.Name)
            mounts=@($item.Mounts | ForEach-Object { @{type=$_.Type;target=$_.Destination;writable=$_.RW} })
        }
    }
    $report = @{status='ok';spec='SPEC-0020';combined_cpu_with_one_job=$cpu;combined_memory_with_one_job=$memory;containers=$safe}
    Write-PrivateFile (Join-Path $localPath 'results/isolation.json') ($report | ConvertTo-Json -Depth 8)
    Write-Host 'Configuration/runtime isolation PASS; sanitized image/resource report saved.'
}
function Check-Ingress {
    $uri = "http://127.0.0.1:$($metadata.port)/api/2.0/mlflow/experiments/search"
    $anon = Invoke-WebRequest -Uri $uri -Method Post -ContentType 'application/json' -Body '{"max_results":1}' -SkipHttpErrorCheck
    if ($anon.StatusCode -ne 401) { throw 'Anonymous request was not rejected by ingress.' }
    $password = (Get-Content -LiteralPath (Join-Path $localPath 'secrets/user_a') -Raw).Trim()
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("analyst_a:$password"))
    $auth = Invoke-WebRequest -Uri $uri -Method Post -ContentType 'application/json' -Body '{"max_results":1}' -Headers @{Authorization="Basic $encoded"} -SkipHttpErrorCheck
    if ($auth.StatusCode -ne 200) { throw 'Authenticated ingress request failed.' }
    Write-PrivateFile (Join-Path $localPath 'results/ingress.json') '{"status":"ok","anonymous_status":401,"authenticated_status":200}'
    Write-Host 'Loopback ingress: anonymous 401, authenticated 200.'
}
$operationLock = $null
try {
    if ($Action -in @('build','up','train','test','stop')) {
        # One operation across every exp03 instance, including all one-off jobs.
        try {
            $operationLock = [IO.File]::Open((Join-Path $PSScriptRoot '.local/operation.lock'),
                [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch { throw 'Another trial operation is active. Wait for it to complete.' }
    }
    if ($Action -in @('up','train','test')) {
        $active = @(& docker ps -q --filter 'label=io.torii.scope=exp03')
        if ($LASTEXITCODE -ne 0) { throw 'Cannot check running trial instances.' }
        $own = @(& docker ps -q --filter 'label=io.torii.scope=exp03' --filter "label=io.torii.instance=$RunId")
        if ($LASTEXITCODE -ne 0) { throw 'Cannot check this trial instance.' }
        if (@($active | Where-Object { $_ -notin $own }).Count -gt 0) { throw 'Another trial instance is active; refusing additional resource allocation.' }
        foreach ($id in $own) {
            $inspection = & docker inspect $id
            if ($LASTEXITCODE -ne 0) { throw 'Cannot verify active trial container.' }
            $item = @($inspection | ConvertFrom-Json)[0]
            $service = $item.Config.Labels.'com.docker.compose.service'
            if ($service -notin @('database','storage','mlflow','gateway') -or $item.Config.Labels.'com.docker.compose.oneoff' -eq 'True') {
                throw 'A trial job is already running outside this harness.'
            }
        }
    }
    switch ($Action) {
        check {
            Invoke-Compose @('config','--quiet')
            Write-Host 'Compose syntax PASS; runtime has not been tested by this action.'
        }
        build { Invoke-Compose @('build','mlflow','database','gateway') }
        up {
            $running = & docker ps -q --filter "label=com.docker.compose.project=$project" --filter 'label=com.docker.compose.service=gateway'
            if (-not $running) { Assert-FreePort $metadata.port }
            Invoke-Compose @('up','--detach','--wait','--wait-timeout','240','database','storage','mlflow','gateway')
            Set-ImageIdentity
            $null = Invoke-Report 'bootstrap' 'TORII_BOOTSTRAP_RESULT=' 'bootstrap'
            Check-Ingress
            Write-Host "MLflow ready: http://127.0.0.1:$($metadata.port) (analyst_a; password in local secret user_a)."
        }
        status { Invoke-Compose @('ps','--all') }
        inspect { Inspect-Isolation; Check-Ingress }
        train {
            Set-ImageIdentity
            $null = Invoke-Report 'train' 'TORII_TRAIN_RESULT=' ('train-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss'))
        }
        test {
            Inspect-Isolation
            Set-ImageIdentity
            $null = Invoke-Report 'bootstrap' 'TORII_BOOTSTRAP_RESULT=' 'bootstrap'
            $first = Invoke-Report 'train' 'TORII_TRAIN_RESULT=' 'train-1'
            $second = Invoke-Report 'train' 'TORII_TRAIN_RESULT=' 'train-2'
            $changed = Invoke-Report 'train' 'TORII_TRAIN_RESULT=' 'train-changed' @('python','train.py','--seed','43')
            foreach ($field in @('data_digest','feature_digest','split_digest','source_digest','transform_digest','image_id')) {
                if ($first.$field -cne $second.$field) { throw "Reproduction mismatch: $field" }
            }
            foreach ($model in @('dummy','ridge')) {
                if ($first.prediction_digests.$model -cne $second.prediction_digests.$model) { throw 'Prediction reproduction mismatch.' }
                if (($first.metrics.$model | ConvertTo-Json -Compress) -cne ($second.metrics.$model | ConvertTo-Json -Compress)) { throw 'Metric reproduction mismatch.' }
                if ($first.run_ids.$model -ceq $second.run_ids.$model) { throw 'Repeated training must have new run IDs.' }
            }
            if ($first.data_digest -ceq $changed.data_digest) { throw 'Changed data must have a new digest.' }
            Write-PrivateFile (Join-Path $localPath 'results/reproduction.json') '{"status":"ok","same_image":true,"same_predictions":true,"same_metrics":true,"changed_data_digest":true}'
            Invoke-Compose @('restart','database','storage','mlflow')
            Invoke-Compose @('up','--detach','--wait','--wait-timeout','240','database','storage','mlflow')
            Verify-Persisted
            Check-Ingress
            $null = Invoke-Report 'access-check' 'TORII_ACCESS_RESULT=' 'access'
            Write-Host 'Trial completed; qualification verdict is in access.json. This does not accept an enterprise adapter.'
        }
        stop {
            Invoke-Compose @('stop')
            Write-Host 'Only this trial stopped; its volumes and credentials are preserved.'
        }
    }
} finally {
    Remove-Item Env:TRIAL_IMAGE_ID -ErrorAction SilentlyContinue
    if ($operationLock) { $operationLock.Dispose() }
}
