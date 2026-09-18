[CmdletBinding()]
param(
    [ValidateSet('3.9', '3.10', '3.11', '3.12')]
    [string]$PythonVersion = '3.12',

    [ValidateSet('vanilla', 'ml-standard', 'ml-max', 'automl-tabular')]
    [string]$Profile = 'ml-standard',

    [string]$ImageRepository = 'torii/workspace',

    [switch]$All,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$pythonVersions = if ($All) { '3.9', '3.10', '3.11', '3.12' } else { $PythonVersion }
$profiles = if ($All) { 'vanilla', 'ml-standard', 'ml-max' } else { $Profile }

foreach ($python in $pythonVersions) {
    foreach ($selectedProfile in $profiles) {
        if ($selectedProfile -eq 'automl-tabular' -and $python -eq '3.9') {
            throw 'The automl-tabular profile requires Python 3.10 or newer because of AutoGluon.'
        }
        $tag = "${ImageRepository}:py${python}-${selectedProfile}"
        $arguments = @(
            'build',
            '--file', 'docker/Dockerfile',
            '--build-arg', "PYTHON_VERSION=${python}",
            '--build-arg', "PROFILE=${selectedProfile}",
            '--tag', $tag,
            '.'
        )

        Write-Host "docker $($arguments -join ' ')"
        if (-not $DryRun) {
            & docker @arguments
            if ($LASTEXITCODE -ne 0) {
                throw "Docker build failed for $tag"
            }
        }
    }
}
