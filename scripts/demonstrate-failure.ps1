param(
    [ValidateSet("http500", "latency", "cpu", "dependency")]
    [string]$Mode = "http500",
    [ValidateRange(30, 300)]
    [int]$DurationSeconds = 120,
    [string]$BaseUrl = "",
    [string]$AdminToken = ""
)

$ErrorActionPreference = "Stop"

if (-not $BaseUrl) {
    $tfState = Join-Path (Split-Path $PSScriptRoot -Parent) "infrastructure/environments/dev/terraform.tfstate"
    if (Test-Path $tfState) {
        try {
            $stateJson = Get-Content $tfState -Raw | ConvertFrom-Json
            $inst = $stateJson.resources | Where-Object { $_.type -eq "aws_instance" } | Select-Object -First 1
            $detectedIp = $inst.instances[0].attributes.public_ip
            if ($detectedIp) {
                $BaseUrl = "http://${detectedIp}:80"
                Write-Host "Auto-detected EC2 Ingress Gateway: $BaseUrl" -ForegroundColor Cyan
            }
        } catch {}
    }
}

if (-not $BaseUrl) {
    $BaseUrl = "http://localhost:80"
}

# Resolve Admin Token: 1. AWS SSM Parameter Store -> 2. .env file -> 3. Fallback default
if (-not $AdminToken) {
    try {
        $ssmVal = aws ssm get-parameter --name "/cloud-native-observability/failure-admin-token" --with-decryption --query "Parameter.Value" --output text 2>$null
        if ($ssmVal -and $LASTEXITCODE -eq 0) {
            $AdminToken = $ssmVal.Trim()
            Write-Host "Loaded FAILURE_ADMIN_TOKEN from AWS SSM Parameter Store." -ForegroundColor Green
        }
    } catch {}
}

if (-not $AdminToken) {
    $envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
    if ($envFile -and (Test-Path $envFile)) {
        $envLine = Get-Content $envFile | Where-Object { $_ -match '^FAILURE_ADMIN_TOKEN=' } | Select-Object -First 1
        if ($envLine) {
            $AdminToken = ($envLine -split '=', 2)[1].Trim().Trim('"')
        }
    }
}

if (-not $AdminToken) {
    $AdminToken = "change-me-on-first-start"
}

$headers = @{ "X-Failure-Token" = $AdminToken }
$failureUrl = "$BaseUrl/admin/failure?mode=$Mode&duration_seconds=$DurationSeconds"

Write-Host "Starting $Mode failure for $DurationSeconds seconds via Gateway..." -ForegroundColor Yellow
Invoke-RestMethod -Method Post -Headers $headers -Uri $failureUrl | Out-Null

$uri = [System.Uri]$BaseUrl
$hostName = $uri.Host

Write-Host ""
Write-Host "Operations & Observability Access:" -ForegroundColor Cyan
Write-Host "  Service A (Gateway):   $BaseUrl/health"
Write-Host "  Grafana (Gateway):     $BaseUrl/grafana/"
Write-Host "  Circuit Breaker:       $BaseUrl/admin/circuit-breaker"
Write-Host "  Prometheus/Alertmgr:   Securely isolated on localhost."
Write-Host "                         Tunnel command: ssh -L 9090:localhost:9090 -L 9093:localhost:9093 ec2-user@${hostName}"
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
Write-Host "Failure disabled." -ForegroundColor Green
