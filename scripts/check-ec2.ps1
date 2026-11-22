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

Write-Host "Instance: $instanceId"
Write-Host "Public IP: $ip"

$description = aws ec2 describe-instances `
    --region $Region `
    --instance-ids $instanceId `
    --query "Reservations[0].Instances[0].{State:State.Name,Status:StatusChecks.InstanceStatus.Status}" `
    --output json

Write-Output $description

if ($ip) {
    $ports = @(8080, 8081, 9090, 9093, 3000)
    foreach ($port in $ports) {
        $path = if ($port -eq 8080 -or $port -eq 8081) { "/health" } else { "" }
        $url = "http://${ip}:${port}${path}"
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
            Write-Host "${url} -> $($response.StatusCode)"
        } catch {
            Write-Host "${url} -> unreachable"
        }
    }
}
