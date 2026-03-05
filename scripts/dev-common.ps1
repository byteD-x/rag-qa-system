Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:DevStateDir = Join-Path $script:RepoRoot "logs\dev"
$script:FrontendPidFile = Join-Path $script:DevStateDir "frontend.pid"
$script:FrontendLogFile = Join-Path $script:DevStateDir "frontend.log"
$script:ComposeServicesCache = $null

function Get-RepoRoot {
    return $script:RepoRoot
}

function Get-DevStateDir {
    return $script:DevStateDir
}

function Get-FrontendPidFile {
    return $script:FrontendPidFile
}

function Get-FrontendLogFile {
    return $script:FrontendLogFile
}

function Ensure-DevStateDir {
    if (-not (Test-Path $script:DevStateDir)) {
        New-Item -ItemType Directory -Path $script:DevStateDir -Force | Out-Null
    }
}

function Test-CommandInstalled {
    param(
        [Parameter(Mandatory = $true)][string]$Name
    )

    return ($null -ne (Get-Command $Name -ErrorAction SilentlyContinue))
}

function Assert-CommandInstalled {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$InstallHint = ""
    )

    if (Test-CommandInstalled -Name $Name) {
        return
    }

    if ($InstallHint) {
        throw "$Name not found. $InstallHint"
    }

    throw "$Name not found."
}

function Test-DockerReady {
    if (-not (Test-CommandInstalled -Name "docker")) {
        return $false
    }

    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Assert-DockerReady {
    Assert-CommandInstalled -Name "docker" -InstallHint "Install Docker Desktop first."
    if (-not (Test-DockerReady)) {
        throw "Docker daemon is not running. Start Docker Desktop first."
    }
}

function Assert-EnvFile {
    $envFile = Join-Path $script:RepoRoot ".env"
    if (Test-Path $envFile) {
        return
    }

    throw ".env file not found. Copy .env.example to .env and fill in the required values first."
}

function Invoke-DockerCompose {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed."
    }
}

function Invoke-DockerComposeCapture {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $output = & docker compose @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine

    if ($exitCode -ne 0) {
        if ($text.Trim()) {
            throw $text.Trim()
        }

        throw "docker compose $($Arguments -join ' ') failed."
    }

    return $text.TrimEnd()
}

function Get-ComposeServices {
    if ($null -ne $script:ComposeServicesCache) {
        return $script:ComposeServicesCache
    }

    $raw = Invoke-DockerComposeCapture -Arguments @("config", "--services")
    $services = @(
        $raw -split "`r?`n" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )

    if ($services.Count -eq 0) {
        throw "No compose services found."
    }

    $script:ComposeServicesCache = $services
    return $script:ComposeServicesCache
}

function Test-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
    }
    catch {
        return $false
    }
}

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Name,
        [int]$RetryCount = 60,
        [int]$RetryIntervalSeconds = 2
    )

    for ($attempt = 1; $attempt -le $RetryCount; $attempt++) {
        if (Test-HttpOk -Url $Url) {
            Write-Host "[OK] $Name ready: $Url"
            return
        }

        Start-Sleep -Seconds $RetryIntervalSeconds
    }

    throw "[FAIL] $Name readiness timeout: $Url"
}

function Wait-CoreServices {
    param(
        [int]$RetryCount = 60,
        [int]$RetryIntervalSeconds = 2
    )

    $targets = @(
        [PSCustomObject]@{
            Name = "go-api"
            Url  = "http://localhost:8080/healthz?depth=basic"
        },
        [PSCustomObject]@{
            Name = "py-rag-service"
            Url  = "http://localhost:8000/healthz?depth=basic"
        }
    )

    foreach ($target in $targets) {
        Wait-HttpOk -Url $target.Url -Name $target.Name -RetryCount $RetryCount -RetryIntervalSeconds $RetryIntervalSeconds
    }
}

function Get-ManagedFrontendPid {
    Ensure-DevStateDir

    if (-not (Test-Path $script:FrontendPidFile)) {
        return $null
    }

    $raw = Get-Content -Path $script:FrontendPidFile -TotalCount 1 -ErrorAction SilentlyContinue
    if ($null -eq $raw) {
        Remove-Item -Path $script:FrontendPidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $raw = $raw.Trim()
    if (-not $raw) {
        Remove-Item -Path $script:FrontendPidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $parsedPid = 0
    if (-not [int]::TryParse($raw, [ref]$parsedPid)) {
        Remove-Item -Path $script:FrontendPidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $proc = Get-Process -Id $parsedPid -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Remove-Item -Path $script:FrontendPidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    return $parsedPid
}

function Stop-ManagedFrontend {
    $frontendProcessId = Get-ManagedFrontendPid
    if ($null -eq $frontendProcessId) {
        return $false
    }

    & taskkill /PID $frontendProcessId /T /F *> $null
    $exitCode = $LASTEXITCODE
    Remove-Item -Path $script:FrontendPidFile -Force -ErrorAction SilentlyContinue

    if ($exitCode -ne 0) {
        Write-Host "[WARN] Failed to stop frontend process tree. PID=$frontendProcessId"
        return $false
    }

    Write-Host "[INFO] Frontend process stopped. PID=$frontendProcessId"
    return $true
}

function Ensure-FrontendDependencies {
    $frontendDir = Join-Path $script:RepoRoot "apps\web"
    $packageJson = Join-Path $frontendDir "package.json"
    $lockFile = Join-Path $frontendDir "package-lock.json"
    $nodeModules = Join-Path $frontendDir "node_modules"

    if (-not (Test-Path $packageJson)) {
        throw "apps/web/package.json not found."
    }

    if (Test-Path $nodeModules) {
        return
    }

    Assert-CommandInstalled -Name "npm" -InstallHint "Install Node.js first."

    Write-Host "[INFO] apps/web/node_modules missing. Installing frontend dependencies..."
    Push-Location $frontendDir
    try {
        if (Test-Path $lockFile) {
            & npm ci
        }
        else {
            & npm install
        }

        if ($LASTEXITCODE -ne 0) {
            throw "npm dependency install failed."
        }
    }
    finally {
        Pop-Location
    }
}

function Start-ManagedFrontend {
    param(
        [int]$Port = 5173,
        [switch]$WaitUntilReady,
        [int]$RetryCount = 60,
        [int]$RetryIntervalSeconds = 2
    )

    $frontendDir = Join-Path $script:RepoRoot "apps\web"
    $frontendUrl = "http://localhost:$Port"
    $existingPid = Get-ManagedFrontendPid

    if ($null -ne $existingPid -and (Test-HttpOk -Url $frontendUrl)) {
        Write-Host "[INFO] Frontend already running. PID=$existingPid URL=$frontendUrl"
        return [PSCustomObject]@{
            Url     = $frontendUrl
            Pid     = $existingPid
            Managed = $true
        }
    }

    if ($null -ne $existingPid) {
        Write-Host "[WARN] Removing stale frontend process. PID=$existingPid"
        Stop-ManagedFrontend | Out-Null
    }

    if (Test-HttpOk -Url $frontendUrl) {
        Write-Host "[INFO] Frontend already running outside managed script: $frontendUrl"
        return [PSCustomObject]@{
            Url     = $frontendUrl
            Pid     = $null
            Managed = $false
        }
    }

    Ensure-FrontendDependencies
    Ensure-DevStateDir

    $command = "npm run dev -- --host 0.0.0.0 --port $Port >> `"$script:FrontendLogFile`" 2>&1"
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/d", "/c", $command -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru
    Set-Content -Path $script:FrontendPidFile -Value "$($proc.Id)" -NoNewline
    Start-Sleep -Seconds 1

    $runningProc = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if ($null -eq $runningProc) {
        Remove-Item -Path $script:FrontendPidFile -Force -ErrorAction SilentlyContinue
        $details = ""
        if (Test-Path $script:FrontendLogFile) {
            $details = (Get-Content -Path $script:FrontendLogFile -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }

        if ($details) {
            throw "Frontend process exited early.`n$details"
        }

        throw "Frontend process exited early."
    }

    Write-Host "[INFO] Frontend process started. PID=$($proc.Id) URL=$frontendUrl"

    if ($WaitUntilReady) {
        try {
            Wait-HttpOk -Url $frontendUrl -Name "frontend" -RetryCount $RetryCount -RetryIntervalSeconds $RetryIntervalSeconds
        }
        catch {
            Stop-ManagedFrontend | Out-Null
            throw
        }
    }

    return [PSCustomObject]@{
        Url     = $frontendUrl
        Pid     = $proc.Id
        Managed = $true
    }
}

function Write-ProjectSummary {
    param(
        [int]$FrontendPort = 5173,
        [switch]$FrontendSkipped,
        [object]$FrontendInfo = $null
    )

    Write-Host ""
    Write-Host "[DONE] Project is ready."
    Write-Host "API Gateway:   http://localhost:8080"
    Write-Host "RAG Service:   http://localhost:8000"
    Write-Host "MinIO API:     http://localhost:19000"
    Write-Host "MinIO Console: http://localhost:19001"

    if (-not $FrontendSkipped) {
        if ($null -ne $FrontendInfo) {
            Write-Host "Frontend Dev:  $($FrontendInfo.Url)"
            if ($FrontendInfo.Managed) {
                Write-Host "Frontend Log:  $script:FrontendLogFile"
            }
            else {
                Write-Host "Frontend Log:  external process (not managed)"
            }
        }
        else {
            Write-Host "Frontend Dev:  http://localhost:$FrontendPort"
        }
    }

    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  Start:       .\scripts\dev-up.ps1"
    Write-Host "  Stop:        .\scripts\dev-down.ps1"
    Write-Host "  Live logs:   .\logs.bat -f"
    Write-Host "  Export logs: .\scripts\aggregate-logs.ps1"
    Write-Host ""
}
