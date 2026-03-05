[CmdletBinding()]
param(
    [string]$OutputDir = ".\logs\export",
    [int]$Tail = 500,
    [string[]]$Service
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-common.ps1")

function Split-ServiceSelection {
    param(
        [string[]]$RequestedServices
    )

    if (-not $RequestedServices -or $RequestedServices.Count -eq 0) {
        return [PSCustomObject]@{
            DockerServices  = Get-ComposeServices
            IncludeFrontend = $true
        }
    }

    $dockerServices = New-Object System.Collections.Generic.List[string]
    $includeFrontend = $false

    foreach ($item in $RequestedServices) {
        $name = $item.Trim()
        if (-not $name) {
            continue
        }

        if ($name -eq "frontend") {
            $includeFrontend = $true
            continue
        }

        $dockerServices.Add($name)
    }

    return [PSCustomObject]@{
        DockerServices  = @($dockerServices)
        IncludeFrontend = $includeFrontend
    }
}

function Get-ComposeLogsText {
    param(
        [Parameter(Mandatory = $true)][string]$ServiceName,
        [Parameter(Mandatory = $true)][int]$LineCount
    )

    $output = & docker compose logs --no-color --tail $LineCount $ServiceName 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine

    return [PSCustomObject]@{
        ExitCode = $exitCode
        Text     = $text.TrimEnd()
    }
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

if ($Tail -le 0) {
    throw "Tail must be greater than 0."
}

$selection = Split-ServiceSelection -RequestedServices $Service
$frontendLogFile = Get-FrontendLogFile
$dockerReady = Test-DockerReady

if (-not $dockerReady -and -not (Test-Path $frontendLogFile)) {
    throw "Docker is unavailable and no managed frontend log file exists."
}

$outputRoot = if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
}
else {
    Join-Path $repoRoot $OutputDir
}

$allDir = Join-Path $outputRoot "ALL"
$errorDir = Join-Path $outputRoot "ERROR"
$warningDir = Join-Path $outputRoot "WARNING"

foreach ($dir in @($outputRoot, $allDir, $errorDir, $warningDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$allLogs = @{}
$errorLines = New-Object System.Collections.Generic.List[string]
$warningLines = New-Object System.Collections.Generic.List[string]
$collectionErrors = New-Object System.Collections.Generic.List[string]

Write-Host "[INFO] Output directory: $outputRoot"

if ($dockerReady) {
    $dockerServices = @($selection.DockerServices)
    if ($dockerServices.Count -gt 0) {
        Write-Host "[INFO] Collecting compose logs for: $($dockerServices -join ', ')"
    }

    foreach ($serviceName in $dockerServices) {
        $result = Get-ComposeLogsText -ServiceName $serviceName -LineCount $Tail
        if ($result.ExitCode -ne 0) {
            $collectionErrors.Add("$serviceName | $($result.Text)")
            Write-Host "[WARN] Failed to collect $serviceName"
            continue
        }

        $allLogs[$serviceName] = $result.Text
        foreach ($line in ($result.Text -split "`r?`n")) {
            if (-not $line.Trim()) {
                continue
            }

            if ($line -match "\b(ERROR|FATAL|CRITICAL)\b") {
                $errorLines.Add("$serviceName | $line")
            }
            elseif ($line -match "\bWARN(ING)?\b") {
                $warningLines.Add("$serviceName | $line")
            }
        }
    }
}
else {
    Write-Host "[WARN] Docker is unavailable. Only frontend log snapshot will be exported."
}

if ($selection.IncludeFrontend) {
    if (Test-Path $frontendLogFile) {
        $frontendLines = Get-Content -Path $frontendLogFile -Tail $Tail -ErrorAction SilentlyContinue
        $frontendText = ($frontendLines | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        $allLogs["frontend"] = $frontendText

        foreach ($line in $frontendLines) {
            if (-not $line.Trim()) {
                continue
            }

            if ($line -match "\b(ERROR|FATAL|CRITICAL)\b") {
                $errorLines.Add("frontend | $line")
            }
            elseif ($line -match "\bWARN(ING)?\b") {
                $warningLines.Add("frontend | $line")
            }
        }
    }
    else {
        $collectionErrors.Add("frontend | managed frontend log file not found")
    }
}

if ($allLogs.Count -eq 0) {
    throw "No logs were collected."
}

foreach ($serviceName in ($allLogs.Keys | Sort-Object)) {
    $targetFile = Join-Path $allDir "$serviceName.log"
    $allLogs[$serviceName] | Out-File -FilePath $targetFile -Encoding utf8
    Write-Host "[OK] $targetFile"
}

if ($errorLines.Count -gt 0) {
    $errorFile = Join-Path $errorDir "errors_$timestamp.log"
    $errorLines | Out-File -FilePath $errorFile -Encoding utf8
    Write-Host "[OK] $errorFile"
}

if ($warningLines.Count -gt 0) {
    $warningFile = Join-Path $warningDir "warnings_$timestamp.log"
    $warningLines | Out-File -FilePath $warningFile -Encoding utf8
    Write-Host "[OK] $warningFile"
}

$summary = @()
$summary += "RAG QA System log export"
$summary += "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$summary += "Tail: $Tail"
$summary += ""
$summary += "Collected services:"
$summary += ($allLogs.Keys | Sort-Object | ForEach-Object { "- $_" })
$summary += ""
$summary += "Error lines: $($errorLines.Count)"
$summary += "Warning lines: $($warningLines.Count)"
$summary += "Collection failures: $($collectionErrors.Count)"

if ($collectionErrors.Count -gt 0) {
    $summary += ""
    $summary += "Collection failures:"
    $summary += ($collectionErrors | ForEach-Object { "- $_" })
}

$summaryFile = Join-Path $outputRoot "summary_$timestamp.txt"
$summary | Out-File -FilePath $summaryFile -Encoding utf8
Write-Host "[OK] $summaryFile"
