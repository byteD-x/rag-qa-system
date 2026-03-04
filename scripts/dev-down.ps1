param(
    [switch]$RemoveVolumes,
    [switch]$RemoveImages,
    [switch]$RemoveAll,
    [switch]$SkipConfirm
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

$composeArgs = @("compose", "down")

if ($RemoveAll) {
    $composeArgs += @("--volumes", "--rmi", "all", "--remove-orphans")
    Write-Host "[WARN] --RemoveAll specified: will remove volumes, all images, and orphan containers."
}
else {
    if ($RemoveVolumes) {
        $composeArgs += "--volumes"
        Write-Host "[WARN] --RemoveVolumes specified: will remove named volumes."
    }
    if ($RemoveImages) {
        $composeArgs += @("--rmi", "all")
        Write-Host "[WARN] --RemoveImages specified: will remove all images."
    }
}

if (-not $SkipConfirm) {
    $confirmMsg = "This will stop and remove running containers."
    if ($RemoveVolumes) { $confirmMsg += " Data volumes will be REMOVED." }
    if ($RemoveImages) { $confirmMsg += " Images will be REMOVED." }
    $confirmMsg += " Continue?"
    
    $confirmation = Read-Host -Prompt "$confirmMsg (y/N)"
    if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
        Write-Host "[CANCEL] Operation cancelled by user."
        exit 0
    }
}

Write-Host "[INFO] Stopping services..."
docker @composeArgs

Write-Host ""
Write-Host "[DONE] Development environment stopped."
if ($RemoveVolumes) {
    Write-Host "[WARN] Named volumes have been removed. All persistent data is lost."
}
if ($RemoveImages) {
    Write-Host "[WARN] Images have been removed. Next startup will require rebuilding."
}
Write-Host ""
Write-Host "To start again, run: .\scripts\dev-up.ps1"
