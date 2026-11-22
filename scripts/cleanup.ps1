param(
    [switch]$Docker,
    [switch]$Terraform,
    [switch]$All
)

$ErrorActionPreference = "Stop"
$rootDir = Split-Path $PSScriptRoot -Parent

Write-Host "Starting cleanup..." -ForegroundColor Cyan

# Clean temporary Python & test caches
Get-ChildItem -Path $rootDir -Include "__pycache__", ".pytest_cache" -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\\.venv\\' } |
    ForEach-Object {
        Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
        Write-Host "Removed cache: $($_.FullName)"
    }

# Remove temporary artifacts
$tempArtifacts = @(
    (Join-Path $rootDir "ai-engine/model.joblib"),
    (Join-Path $rootDir "infrastructure/environments/dev/terraform.tfstate"),
    (Join-Path $rootDir "infrastructure/environments/dev/terraform.tfstate.backup")
)
foreach ($artifact in $tempArtifacts) {
    if (Test-Path $artifact) {
        Remove-Item -Force $artifact -ErrorAction SilentlyContinue
        Write-Host "Removed temporary artifact: $artifact"
    }
}

# Stop Docker Compose if requested
if ($Docker -or $All) {
    Write-Host "Stopping Docker Compose services..." -ForegroundColor Yellow
    docker compose -f (Join-Path $rootDir "docker-compose.yml") down -v --remove-orphans
}

# Destroy Terraform infrastructure if requested
if ($Terraform -or $All) {
    Write-Host "Destroying Terraform resources..." -ForegroundColor Yellow
    Push-Location (Join-Path $rootDir "infrastructure/environments/dev")
    try {
        terraform destroy -auto-approve
    } finally {
        Pop-Location
    }
}

Write-Host "Cleanup completed successfully." -ForegroundColor Green
