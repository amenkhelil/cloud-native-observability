param(
    [string]$PublicIp = "",
    [string]$StateFile = "infrastructure/environments/dev/terraform.tfstate",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"
$statePath = Resolve-Path $StateFile
$state = Get-Content $statePath -Raw | ConvertFrom-Json
$instance = $state.resources |
    Where-Object { $_.type -eq "aws_instance" } |
    Select-Object -First 1

if (-not $instance) {
    throw "No EC2 instance found in the Terraform state."
}

$instanceId = $instance.instances[0].attributes.id
$ip = if ($PublicIp) { $PublicIp } else { $instance.instances[0].attributes.public_ip }

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "EC2 Ingress & Security Verification" -ForegroundColor Cyan
Write-Host "Instance:  $instanceId"
Write-Host "Public IP: $ip"
Write-Host "==========================================" -ForegroundColor Cyan

$description = aws ec2 describe-instances `
    --region $Region `
    --instance-ids $instanceId `
    --query "Reservations[0].Instances[0].{State:State.Name,Status:StatusChecks.InstanceStatus.Status}" `
    --output json

Write-Output $description

if ($ip) {
    Write-Host "`n1. Verifying Public Gateway Ingress (Port 80 & 443)..." -ForegroundColor Yellow
    $gatewayEndpoints = @(
        @{ Name = "Gateway Health (HTTP)"; Url = "http://${ip}:80/healthz" },
        @{ Name = "Service A via Ingress"; Url = "http://${ip}:80/health" },
        @{ Name = "Grafana via Ingress"; Url = "http://${ip}:80/grafana/api/health" }
    )

    foreach ($ep in $gatewayEndpoints) {
        try {
            $response = Invoke-WebRequest -Uri $ep.Url -UseBasicParsing -TimeoutSec 5
            Write-Host "  [OK] $($ep.Name): $($ep.Url) -> $($response.StatusCode)" -ForegroundColor Green
        } catch {
            Write-Host "  [FAIL] $($ep.Name): $($ep.Url) -> unreachable" -ForegroundColor Red
        }
    }

    Write-Host "`n2. Verifying Security Isolation (Internal Ports MUST be unreachable from public internet)..." -ForegroundColor Yellow
    $isolatedPorts = @(8080, 8081, 9090, 9093, 3000)
    foreach ($port in $isolatedPorts) {
        $testUrl = "http://${ip}:${port}/"
        try {
            $resp = Invoke-WebRequest -Uri $testUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            Write-Host "  [WARNING] Port $port is exposed: $testUrl returned $($resp.StatusCode)" -ForegroundColor Red
        } catch {
            Write-Host "  [SECURE] Port $port correctly blocked by Security Group (unreachable)" -ForegroundColor Green
        }
    }

    Write-Host "`n3. Administrative Telemetry Access (SSH Tunneling):" -ForegroundColor Cyan
    Write-Host "  Prometheus and Alertmanager are isolated on host loopback (127.0.0.1)."
    Write-Host "  To access them securely from your workstation, open an SSH tunnel:"
    Write-Host "    ssh -i <your-key.pem> -L 9090:localhost:9090 -L 9093:localhost:9093 ec2-user@${ip}"
    Write-Host "  Then open in browser:"
    Write-Host "    Prometheus:   http://localhost:9090"
    Write-Host "    Alertmanager: http://localhost:9093"
}
