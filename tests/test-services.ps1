[CmdletBinding()]
param(
    [string]$Image = 'torii/workspace:py3.12-vanilla'
)

$ErrorActionPreference = 'Stop'
$jupyterContainer = 'torii-test-jupyter'
$codeContainer = 'torii-test-code-server'
$containerNames = $jupyterContainer, $codeContainer

$existing = docker ps -a --format '{{.Names}}'
foreach ($name in $containerNames) {
    if ($existing -contains $name) {
        throw "Refusing to replace an existing container: $name"
    }
}

try {
    docker run --detach `
        --name $jupyterContainer `
        --publish 127.0.0.1:18888:8888 `
        --env WORKSPACE_AUTH_MODE=token `
        --env JUPYTER_TOKEN=local-test-token `
        $Image | Out-Null

    docker run --detach `
        --name $codeContainer `
        --publish 127.0.0.1:18080:8080 `
        --env WORKSPACE_IDE=code-server `
        --env WORKSPACE_AUTH_MODE=password `
        --env PASSWORD=local-test-password `
        $Image | Out-Null

    $jupyterReady = $false
    $codeServerReady = $false

    foreach ($attempt in 1..20) {
        try {
            $jupyterResponse = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri 'http://127.0.0.1:18888/lab?token=local-test-token' `
                -TimeoutSec 2
            $jupyterReady = $jupyterResponse.StatusCode -eq 200
        } catch {
            $jupyterReady = $false
        }

        try {
            $codeServerResponse = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri 'http://127.0.0.1:18080/healthz' `
                -TimeoutSec 2
            $codeServerReady = $codeServerResponse.StatusCode -eq 200
        } catch {
            $codeServerReady = $false
        }

        if ($jupyterReady -and $codeServerReady) {
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $jupyterReady) {
        docker logs $jupyterContainer
        throw 'JupyterLab did not become ready'
    }
    if (-not $codeServerReady) {
        docker logs $codeContainer
        throw 'code-server did not become ready'
    }

    foreach ($name in $containerNames) {
        $uid = docker exec $name id -u
        if ($uid -ne '1001') {
            throw "$name runs with unexpected UID $uid"
        }
        docker exec $name test -f /workspace/.automl-scaffold-version
        if ($LASTEXITCODE -ne 0) {
            throw "Scaffold marker is missing in $name"
        }
    }

    Write-Host 'JupyterLab HTTP test: passed'
    Write-Host 'code-server HTTP test: passed'
    Write-Host 'Non-root UID and scaffold tests: passed'
} finally {
    foreach ($name in $containerNames) {
        if ((docker ps -a --format '{{.Names}}') -contains $name) {
            docker rm --force $name | Out-Null
        }
    }
}
