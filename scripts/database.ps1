# Use the project's Python directly, without activating it or changing PATH.
param(
    [ValidateSet('setup', 'start', 'stop', 'status', 'prepare')]
    [string]$Action = 'status'
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
$databaseHelper = Join-Path $projectRoot 'backend/docker_database.py'

if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'The project Python environment is missing. Follow the Python setup steps in README.md.'
}

& $projectPython $databaseHelper $Action
exit $LASTEXITCODE
