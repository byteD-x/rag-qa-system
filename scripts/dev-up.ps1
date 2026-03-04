param(
    [switch]$NoBuild,
    [switch]$SkipFrontend,
    [switch]$SkipHealthCheck,
    [int]$FrontendPort = 5173,
    [int]$MaxRetry = 30,
    [int]$RetryIntervalSeconds = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Name,
        [int]$Retry = 30,
        [int]$IntervalSeconds = 2
    )

    for ($i = 1; $i -le $Retry; $i++) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
                Write-Host "[OK] $Name healthy: $Url"
                return
            }
        }
        catch {
            Start-Sleep -Seconds $IntervalSeconds
        }
    }

    throw "[FAIL] $Name health check timeout: $Url"
}

function Test-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url
    )

    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
    }
    catch {
        return $false
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

Write-Host "[INFO] Repo root: $repoRoot"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Please install Docker Desktop first."
}

try {
    docker info *> $null
}
catch {
    throw "Docker daemon is not running. Please start Docker Desktop first."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[INFO] .env not found, copied from .env.example"
}

$composeArgs = @("compose", "up", "-d")
if (-not $NoBuild) {
    $composeArgs += "--build"
}

docker @composeArgs

if (-not $SkipHealthCheck) {
    Wait-HttpOk -Url "http://localhost:8080/healthz" -Name "go-api" -Retry $MaxRetry -IntervalSeconds $RetryIntervalSeconds
    Wait-HttpOk -Url "http://localhost:8000/healthz" -Name "py-rag-service" -Retry $MaxRetry -IntervalSeconds $RetryIntervalSeconds
}

$frontendUrl = "http://localhost:$FrontendPort"
if ($SkipFrontend) {
    Write-Host "[INFO] Skip frontend startup by -SkipFrontend"
}
elseif (Test-HttpOk -Url $frontendUrl) {
    Write-Host "[INFO] Frontend already running: $frontendUrl"
}
else {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not found. Please install Node.js (includes npm) first."
    }

    $frontendDir = Join-Path $repoRoot "frontend"
    if (-not (Test-Path (Join-Path $frontendDir "package.json"))) {
        throw "frontend/package.json not found."
    }
    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        throw "frontend/node_modules not found. Run 'cd frontend; npm ci' first."
    }

    $frontendCmd = "Set-Location -LiteralPath '$frontendDir'; npm run dev -- --host 0.0.0.0 --port $FrontendPort"
    $frontendProc = Start-Process -FilePath "powershell" -ArgumentList "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCmd -PassThru
    Write-Host "[INFO] Frontend dev server started in a new process. PID=$($frontendProc.Id)"

    if (-not $SkipHealthCheck) {
        Wait-HttpOk -Url $frontendUrl -Name "frontend" -Retry $MaxRetry -IntervalSeconds $RetryIntervalSeconds
    }
}

docker compose ps

Write-Host ""
Write-Host "[DONE] Development environment is ready."
Write-Host "- API Gateway:    http://localhost:8080"
Write-Host "- RAG Service:    http://localhost:8000"
Write-Host "- Frontend Dev:   $frontendUrl"
Write-Host "- MinIO API:      http://localhost:19000"
Write-Host "- MinIO Console:  http://localhost:19001"
