#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$SkipEncodingCheck,
    [switch]$SkipBackendCompile,
    [switch]$SkipFrontendUnitTests,
    [switch]$SkipFrontendBuild,
    [switch]$SkipDockerConfig,
    [switch]$SkipPytest,
    [switch]$IncludeDockerBuild,
    [int]$PytestTimeoutSeconds = 900,
    [int]$PytestMaxWorkers = 1,
    [int]$PytestIdleTimeoutSeconds = 0,
    [int]$PytestTailLinesOnFailure = 20,
    [int]$PytestTotalTimeoutSeconds = 3600
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\dev\common.ps1")

$repoRoot = Get-RepoRoot
$python = Get-PythonCommandSpec
$failures = New-Object System.Collections.Generic.List[string]
$totalChecks = 0
function Invoke-Check {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    $script:totalChecks++
    Write-Host ""
    Write-Host ("=" * 60)
    Write-Host "[$script:totalChecks] $Name"
    Write-Host ("=" * 60)

    try {
        & $Action
        Write-Ok "$Name passed"
    }
    catch {
        Write-Warn "$Name failed: $($_.Exception.Message)"
        $script:failures.Add($Name)
    }
}

function Invoke-RepoTool {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $repoRoot
    )

    Invoke-ExternalCommand -Command $Command -Arguments $Arguments -WorkingDirectory $WorkingDirectory
}

function Invoke-RepoToolWithTimeout {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $repoRoot,
        [int]$TimeoutSeconds = 900,
        [int]$HeartbeatSeconds = 30
    )

    $logDir = Join-Path $repoRoot "logs\quality"
    Ensure-Directory -Path $logDir
    $safeName = ($Command -replace '[^A-Za-z0-9_.-]', '_')
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdoutPath = Join-Path $logDir "$safeName-$timestamp.out.log"
    $stderrPath = Join-Path $logDir "$safeName-$timestamp.err.log"

    $process = Start-Process `
        -FilePath $Command `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -PassThru `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    $started = Get-Date
    try {
        while (-not $process.HasExited) {
            $waitMs = [Math]::Max([Math]::Min($HeartbeatSeconds, 30), 1) * 1000
            $process.WaitForExit($waitMs) | Out-Null
            $elapsed = [int]((Get-Date) - $started).TotalSeconds
            $stdoutBytes = if (Test-Path $stdoutPath) { (Get-Item $stdoutPath).Length } else { 0 }
            $stderrBytes = if (Test-Path $stderrPath) { (Get-Item $stderrPath).Length } else { 0 }
            Write-Info "Still running after ${elapsed}s: $Command $($Arguments -join ' ') stdout_bytes=$stdoutBytes stderr_bytes=$stderrBytes"
            if ($elapsed -ge $TimeoutSeconds) {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                throw "Command timed out after ${TimeoutSeconds}s: $Command $($Arguments -join ' '). Logs: $stdoutPath $stderrPath"
            }
        }

        $stdout = if (Test-Path $stdoutPath) { Get-Content -Path $stdoutPath -Raw -ErrorAction SilentlyContinue } else { "" }
        $stderr = if (Test-Path $stderrPath) { Get-Content -Path $stderrPath -Raw -ErrorAction SilentlyContinue } else { "" }
        if ($stdout) { Write-Host $stdout.TrimEnd() }
        if ($stderr) { Write-Host $stderr.TrimEnd() }

        if ($process.ExitCode -ne 0) {
            throw ("Command failed with exit code {0}: {1} {2}. Logs: {3} {4}" -f $process.ExitCode, $Command, ($Arguments -join ' '), $stdoutPath, $stderrPath)
        }
    }
    finally {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

if (-not $SkipEncodingCheck) {
    Invoke-Check "Encoding Check" {
        $args = @($python.BaseArguments) + @("scripts/quality/check-encoding.py")
        Invoke-RepoTool -Command $python.Command -Arguments $args
    }
}

if (-not $SkipBackendCompile) {
    Invoke-Check "Python Backend Compile" {
        $args = @($python.BaseArguments) + @(
            "-m",
            "compileall",
            "packages/python",
            "apps/services/api-gateway",
            "apps/services/knowledge-base"
        )
        Invoke-RepoTool -Command $python.Command -Arguments $args
    }
}

if (-not $SkipFrontendBuild) {
    Invoke-Check "Frontend Build" {
        Invoke-RepoTool -Command "npm" -Arguments @("run", "build") -WorkingDirectory (Resolve-RepoPath -RelativePath "apps\web")
    }
}

if (-not $SkipFrontendUnitTests) {
    Invoke-Check "Frontend Unit Tests" {
        Invoke-RepoTool -Command "npm" -Arguments @("run", "test:unit") -WorkingDirectory (Resolve-RepoPath -RelativePath "apps\web")
    }
}

if (-not $SkipDockerConfig) {
    Invoke-Check "Docker Compose Config" {
        Invoke-DockerCompose -Arguments @("config", "--quiet")
    }
}

if (-not $SkipPytest) {
    Invoke-Check "Pytest" {
        $args = @($python.BaseArguments) + @(
            "scripts/quality/run_pytest_groups.py",
            "--timeout-seconds",
            "$PytestTimeoutSeconds",
            "--max-workers",
            "$PytestMaxWorkers",
            "--idle-timeout-seconds",
            "$PytestIdleTimeoutSeconds",
            "--tail-lines-on-failure",
            "$PytestTailLinesOnFailure",
            "tests"
        )
        Invoke-RepoToolWithTimeout -Command $python.Command -Arguments $args -TimeoutSeconds $PytestTotalTimeoutSeconds
    }
}

if ($IncludeDockerBuild) {
    Invoke-Check "Docker Build" {
        Invoke-DockerCompose -Arguments @("build", "--pull")
    }
}

Write-Host ""
Write-Host ("=" * 60)
Write-Host "CI Check Summary"
Write-Host ("=" * 60)
Write-Host "Total checks: $totalChecks"

if ($failures.Count -eq 0) {
    Write-Ok "All checks passed"
    exit 0
}

Write-Warn "$($failures.Count) checks failed"
foreach ($failure in $failures) {
    Write-Host "  - $failure"
}
exit 1
