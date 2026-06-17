#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$SkipDoctor,
    [switch]$SkipEncodingCheck,
    [switch]$SkipBackendCompile,
    [switch]$SkipFrontendUnitTests,
    [switch]$SkipFrontendBuild,
    [switch]$SkipDockerConfig,
    [switch]$SkipPytest,
    [switch]$IncludeDockerBuild,
    [int]$PytestTimeoutSeconds = 900,
    [int]$PytestHeartbeatSeconds = 30,
    [int]$PytestMaxWorkers = 1,
    [int]$PytestIdleTimeoutSeconds = 0,
    [int]$PytestTailLinesOnFailure = 20,
    [int]$PytestTotalTimeoutSeconds = 3600,
    [string[]]$PytestArg = @(),
    [string]$PytestSummaryOutput = "",
    [string[]]$PytestTargets = @("tests")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\dev\common.ps1")

$repoRoot = Get-RepoRoot
$python = Get-PythonCommandSpec
$effectivePytestTargets = @($PytestTargets | Where-Object { $_ -and $_.Trim() })
if ($effectivePytestTargets.Count -eq 0) {
    $effectivePytestTargets = @("tests")
}
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

function Write-NewLogContent {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][ref]$Offset
    )

    if (-not (Test-Path $Path)) {
        return
    }

    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        if ($Offset.Value -gt $stream.Length) {
            $Offset.Value = 0
        }
        $stream.Seek([int64]$Offset.Value, [System.IO.SeekOrigin]::Begin) | Out-Null
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true, 4096, $true)
        try {
            $content = $reader.ReadToEnd()
            $Offset.Value = $stream.Position
        }
        finally {
            $reader.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }

    if ($content) {
        Write-Host $content.TrimEnd()
    }
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

    $started = Get-Date
    $stdoutOffset = 0L
    $stderrOffset = 0L
    $argumentLine = Convert-ToProcessArgumentLine -Arguments $Arguments
    $process = $null
    try {
        $process = Start-Process `
            -FilePath $Command `
            -ArgumentList $argumentLine `
            -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -NoNewWindow `
            -PassThru
        $null = $process.Handle

        while (-not $process.HasExited) {
            $waitMs = [Math]::Max([Math]::Min($HeartbeatSeconds, 30), 1) * 1000
            $process.WaitForExit($waitMs) | Out-Null
            Write-NewLogContent -Path $stdoutPath -Offset ([ref]$stdoutOffset)
            Write-NewLogContent -Path $stderrPath -Offset ([ref]$stderrOffset)
            if ($process.HasExited) {
                break
            }
            $elapsed = [int]((Get-Date) - $started).TotalSeconds
            $stdoutBytes = if (Test-Path $stdoutPath) { (Get-Item $stdoutPath).Length } else { 0 }
            $stderrBytes = if (Test-Path $stderrPath) { (Get-Item $stderrPath).Length } else { 0 }
            Write-Info "Still running after ${elapsed}s: $Command $($Arguments -join ' ') stdout_bytes=$stdoutBytes stderr_bytes=$stderrBytes"
            if ($elapsed -ge $TimeoutSeconds) {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                Write-NewLogContent -Path $stdoutPath -Offset ([ref]$stdoutOffset)
                Write-NewLogContent -Path $stderrPath -Offset ([ref]$stderrOffset)
                throw "Command timed out after ${TimeoutSeconds}s: $Command $($Arguments -join ' '). Logs: $stdoutPath $stderrPath"
            }
        }
        $process.WaitForExit()
        $process.Refresh()
        $exitCode = $process.ExitCode
        Write-NewLogContent -Path $stdoutPath -Offset ([ref]$stdoutOffset)
        Write-NewLogContent -Path $stderrPath -Offset ([ref]$stderrOffset)

        if ($null -eq $exitCode) {
            throw ("Command exited but exit code was not available: {0} {1}. Logs: {2} {3}" -f $Command, ($Arguments -join ' '), $stdoutPath, $stderrPath)
        }
        if ($exitCode -ne 0) {
            throw ("Command failed with exit code {0}: {1} {2}. Logs: {3} {4}" -f $exitCode, $Command, ($Arguments -join ' '), $stdoutPath, $stderrPath)
        }
    }
    finally {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
}

function Convert-ToProcessArgumentLine {
    param([string[]]$Arguments = @())

    $quoted = foreach ($item in $Arguments) {
        $value = [string]$item
        if (-not $value) {
            '""'
        }
        elseif ($value -notmatch '[\s"]') {
            $value
        }
        else {
            '"' + (($value -replace '\\+$', '$0$0') -replace '"', '\"') + '"'
        }
    }
    return ($quoted -join " ")
}

if (-not $SkipDoctor) {
    Invoke-Check "Environment Doctor" {
        $args = @($python.BaseArguments) + @("scripts/quality/doctor.py")
        Invoke-RepoTool -Command $python.Command -Arguments $args
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
        $runnerArgs = @(
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
            $runnerArgs += @("--summary-output", $PytestSummaryOutput)
        }
        foreach ($item in @($PytestArg | Where-Object { $_ -and $_.Trim() })) {
            $runnerArgs += @("--pytest-arg=$item")
        }
        $args = @($python.BaseArguments) + $runnerArgs + $effectivePytestTargets
        Invoke-RepoToolWithTimeout -Command $python.Command -Arguments $args -TimeoutSeconds $PytestTotalTimeoutSeconds -HeartbeatSeconds $PytestHeartbeatSeconds
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
