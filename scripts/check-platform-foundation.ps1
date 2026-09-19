# SPEC-0002 AC-04: local equivalents of the first CI gates, no deployment.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$toriiRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Validation failed: $Command" }
}
Push-Location $toriiRepo
try {
    Invoke-Checked uv @('run', '--python', '3.12', '--no-project', 'specs/0001-project-object-version/validate_contracts.py')
    Push-Location (Join-Path $toriiRepo 'apps/api')
    try {
        Invoke-Checked uv @('sync', '--frozen')
        Invoke-Checked uv @('run', '--frozen', 'ruff', 'check', 'src', 'tests', 'migrations')
        Invoke-Checked uv @('run', '--frozen', 'ruff', 'format', '--check', 'src', 'tests', 'migrations')
        Invoke-Checked uv @('run', '--frozen', 'mypy')
        Invoke-Checked uv @('run', '--frozen', 'pytest', '-q', '--cov')
        Invoke-Checked uv @('export', '--frozen', '--no-dev', '--no-editable', '--no-emit-project', '--output-file', '.venv/runtime-requirements.txt', '--quiet')
        Invoke-Checked uvx @('--from', 'pip-audit==2.10.1', 'pip-audit', '--disable-pip', '--no-deps', '-r', '.venv/runtime-requirements.txt')
    } finally { Pop-Location }
    Push-Location (Join-Path $toriiRepo 'apps/web')
    try {
        Invoke-Checked npm @('ci', '--ignore-scripts')
        Invoke-Checked npm @('run', 'lint')
        Invoke-Checked npm @('run', 'typecheck')
        Invoke-Checked npm @('test')
        Invoke-Checked npm @('run', 'build')
        Invoke-Checked npm @('audit', '--audit-level=low')
    } finally { Pop-Location }
    & (Join-Path $toriiRepo 'deploy/platform/test-tools.ps1')
    Invoke-Checked git @('diff', '--check')
    Write-Host 'Foundation gates PASS. OIDC, project services, E2E, restore, images/SBOM and enterprise qualification remain separate gates.'
} finally { Pop-Location }
