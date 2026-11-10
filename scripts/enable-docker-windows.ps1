# Run once as Administrator. This enables Docker's WSL prerequisites.
# It deliberately does not restart Windows or change the app's database.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDirectory = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Force -Path $localDirectory | Out-Null
$logFile = Join-Path $localDirectory 'docker-windows-prerequisites.log'
$resultFile = Join-Path $localDirectory 'docker-windows-prerequisites.json'

Start-Transcript -Path $logFile -Append | Out-Null
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Open PowerShell as Administrator before running this helper.'
    }

    # NoRestart lets you save your work and restart Windows yourself.
    $features = Enable-WindowsOptionalFeature -Online -All -NoRestart -FeatureName VirtualMachinePlatform,Microsoft-Windows-Subsystem-Linux

    & winget install --id Microsoft.WSL --exact --source winget --silent --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "WSL installation failed (exit $LASTEXITCODE)." }

    @{ status = 'ready'; restartRequired = [bool]($features.RestartNeeded -contains $true) } |
        ConvertTo-Json | Set-Content -LiteralPath $resultFile
    Write-Output 'Prerequisites installed. Save your work and restart Windows before starting Docker.'
} catch {
    @{ status = 'failed'; message = $_.Exception.Message } |
        ConvertTo-Json | Set-Content -LiteralPath $resultFile
    throw
} finally {
    Stop-Transcript | Out-Null
}
