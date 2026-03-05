[CmdletBinding()]
param(
    [switch]$NoBuild,
    [switch]$SkipFrontend,
    [switch]$SkipHealthCheck,
    [switch]$AttachLogs,
    [int]$FrontendPort = 5173,
    [int]$RetryCount = 60,
    [int]$RetryIntervalSeconds = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-common.ps1")

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

Write-Host "[INFO] Repo root: $repoRoot"
Assert-DockerReady
Assert-EnvFile

$services = Get-ComposeServices
Write-Host "[INFO] Compose services: $($services -join ', ')"

$composeArgs = @("up", "-d", "--remove-orphans")
if ($NoBuild) {
    Write-Host "[INFO] Skipping image build."
}
else {
    $composeArgs += "--build"
    Write-Host "[INFO] Building changed images before startup."
}

Write-Host "[INFO] Starting Docker services..."
Invoke-DockerCompose -Arguments $composeArgs

if (-not $SkipHealthCheck) {
    Write-Host "[INFO] Waiting for core HTTP services..."
    Wait-CoreServices -RetryCount $RetryCount -RetryIntervalSeconds $RetryIntervalSeconds
}
else {
    Write-Host "[INFO] Health checks skipped."
}

$frontendInfo = $null
if ($SkipFrontend) {
    Write-Host "[INFO] Frontend startup skipped."
}
else {
    $frontendInfo = Start-ManagedFrontend -Port $FrontendPort -WaitUntilReady:(-not $SkipHealthCheck) -RetryCount $RetryCount -RetryIntervalSeconds $RetryIntervalSeconds
}

Write-Host ""
Write-Host "[INFO] Active containers:"
Invoke-DockerCompose -Arguments @("ps")

Write-ProjectSummary -FrontendPort $FrontendPort -FrontendSkipped:$SkipFrontend -FrontendInfo $frontendInfo

if ($AttachLogs) {
    $logsScript = Join-Path $repoRoot "logs.bat"
    Write-Host "[INFO] Attaching real-time logs. Press Ctrl+C to stop log streaming."
    & $logsScript -f
    if ($LASTEXITCODE -notin @(0, 130)) {
        throw "Real-time log viewer exited with code $LASTEXITCODE."
    }
}
