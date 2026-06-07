[CmdletBinding()]
param(
    [int]$PytestTimeoutSeconds = 900,
    [int]$PytestHeartbeatSeconds = 30,
    [int]$PytestMaxWorkers = 1,
    [int]$PytestIdleTimeoutSeconds = 0,
    [int]$PytestTailLinesOnFailure = 20,
    [string[]]$PytestArg = @(),
    [string]$PytestSummaryOutput = "",
    [string[]]$PytestTargets = @("tests")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

try {
    $repoRoot = Get-RepoRoot
    $python = Get-PythonCommandSpec
    $effectivePytestTargets = @($PytestTargets | Where-Object { $_ -and $_.Trim() })
    if ($effectivePytestTargets.Count -eq 0) {
        $effectivePytestTargets = @("tests")
    }
    Set-Location $repoRoot

    Write-Info "Repo root: $repoRoot"
    Assert-DockerReady
    Assert-EnvFile

    Write-Info "Checking text encodings..."
    Invoke-ExternalCommand -Command $python.Command -Arguments (@($python.BaseArguments) + @("scripts/quality/check-encoding.py"))

    Write-Info "Building frontend..."
    Invoke-ExternalCommand -Command "npm" -Arguments @("run", "build") -WorkingDirectory (Join-Path $repoRoot "apps/web")

    Write-Info "Running frontend unit tests..."
    Invoke-ExternalCommand -Command "npm" -Arguments @("run", "test:unit") -WorkingDirectory (Join-Path $repoRoot "apps/web")

    Write-Info "Compiling Python services..."
    Invoke-ExternalCommand -Command $python.Command -Arguments (@($python.BaseArguments) + @("-m", "compileall", "packages/python", "apps/services/api-gateway", "apps/services/knowledge-base"))

    Write-Info "Running backend test suite..."
    $pytestArgs = @(
        "scripts/quality/run_pytest_groups.py",
        "--timeout-seconds",
        "$PytestTimeoutSeconds",
        "--heartbeat-seconds",
        "$PytestHeartbeatSeconds",
        "--max-workers",
        "$PytestMaxWorkers",
        "--idle-timeout-seconds",
        "$PytestIdleTimeoutSeconds",
        "--tail-lines-on-failure",
        "$PytestTailLinesOnFailure"
    )
    if ($PytestSummaryOutput -and $PytestSummaryOutput.Trim()) {
        $pytestArgs += @("--summary-output", $PytestSummaryOutput)
    }
    foreach ($item in @($PytestArg | Where-Object { $_ -and $_.Trim() })) {
        $pytestArgs += @("--pytest-arg=$item")
    }
    Invoke-ExternalCommand -Command $python.Command -Arguments (@($python.BaseArguments) + $pytestArgs + $effectivePytestTargets)

    Write-Info "Validating compose config..."
    Invoke-ExternalCommand -Command "docker" -Arguments @("compose", "config", "--quiet")

    Write-Ok "Preflight checks completed"
}
catch {
    Write-Host "[FAIL] $($_.Exception.Message)"
    exit 1
}
