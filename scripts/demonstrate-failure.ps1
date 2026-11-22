param(
    [ValidateSet("http500", "latency", "cpu", "dependency")]
    [string]$Mode = "http500",
    [ValidateRange(30, 300)]
    [int]$DurationSeconds = 120,
    [string]$BaseUrl = "http://localhost:8080",
    [string]$AdminToken = "change-me-on-first-start"
)

$ErrorActionPreference = "Stop"

if ($BaseUrl -match '^https?://(:|/)' -or $BaseUrl -eq "http://localhost:8080") {
    $tfState = Join-Path (Split-Path $PSScriptRoot -Parent) "infrastructure/environments/dev/terraform.tfstate"
    if (Test-Path $tfState) {
        try {
            $stateJson = Get-Content $tfState -Raw | ConvertFrom-Json
            $inst = $stateJson.resources | Where-Object { $_.type -eq "aws_instance" } | Select-Object -First 1
            $detectedIp = $inst.instances[0].attributes.public_ip
            if ($detectedIp) {
                $BaseUrl = "http://${detectedIp}:8080"
                Write-Host "Auto-detected EC2 Public IP: $detectedIp"
            }
        } catch {}
    }
}

$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if ($envFile -and (Test-Path $envFile)) {
    $envLine = Get-Content $envFile | Where-Object { $_ -match '^FAILURE_ADMIN_TOKEN=' } | Select-Object -First 1
    if ($envLine) {
        $AdminToken = ($envLine -split '=', 2)[1].Trim().Trim('"')
    }
}
$headers = @{ "X-Failure-Token" = $AdminToken }
$failureUrl = "$BaseUrl/admin/failure?mode=$Mode&duration_seconds=$DurationSeconds"

Write-Host "Starting $Mode failure for $DurationSeconds seconds..."
Invoke-RestMethod -Method Post -Headers $headers -Uri $failureUrl | Out-Null

$uri = [System.Uri]$BaseUrl
$hostName = $uri.Host

Write-Host ""
Write-Host "Dashboards & Alerts URLs (open now):" -ForegroundColor Cyan
Write-Host "  Prometheus:   http://${hostName}:9090/alerts"
Write-Host "  Alertmanager: http://${hostName}:9093"
Write-Host "  Grafana:      http://${hostName}:3000"
Write-Host "  Circuit Brk:  http://${hostName}:8080/admin/circuit-breaker"
Write-Host ""
Write-Host "Generating failure traffic continuously for $DurationSeconds seconds..."

$endTime = (Get-Date).AddSeconds($DurationSeconds)
$count = 0
$errors = 0

while ((Get-Date) -lt $endTime) {
    $count++
    try {
        Invoke-RestMethod -Uri "$BaseUrl/api/process" -TimeoutSec 5 | Out-Null
    } catch {
        $errors++
    }
    
    if ($count % 10 -eq 0) {
        $remaining = [math]::Max(0, [int]($endTime - (Get-Date)).TotalSeconds)
        Write-Host ("  [{0}s remaining] Sent {1} requests ({2} errors) -> Alert status: Pending (0-30s) -> FIRING (30s+)" -f $remaining, $count, $errors)
    }
    Start-Sleep -Milliseconds 500
}

Invoke-RestMethod -Method Post -Headers $headers `
    -Uri "$BaseUrl/admin/failure?mode=&duration_seconds=60" | Out-Null
Write-Host "Failure disabled."
