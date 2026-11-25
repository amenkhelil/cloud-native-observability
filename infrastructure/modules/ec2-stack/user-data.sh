#!/bin/bash
set -euo pipefail

exec > >(tee -a /var/log/cloud-native-observability-bootstrap.log) 2>&1
echo "Bootstrap started: $(date -u +%FT%TZ)"

dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user || true

mkdir -p /usr/libexec/docker/cli-plugins
curl -sSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m) -o /usr/libexec/docker/cli-plugins/docker-compose
chmod +x /usr/libexec/docker/cli-plugins/docker-compose
ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose
ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/bin/docker-compose

curl -sSL https://github.com/docker/buildx/releases/download/v0.21.1/buildx-v0.21.1.linux-amd64 -o /usr/libexec/docker/cli-plugins/docker-buildx
chmod +x /usr/libexec/docker/cli-plugins/docker-buildx
ln -sf /usr/libexec/docker/cli-plugins/docker-buildx /usr/local/bin/docker-buildx
ln -sf /usr/libexec/docker/cli-plugins/docker-buildx /usr/bin/docker-buildx

mkdir -p /opt/cloud-native-observability
cd /opt/cloud-native-observability

if [ -n "${git_repo_url}" ]; then
  echo "Cloning repository from ${git_repo_url}..."
  rm -rf /opt/cloud-native-observability/* 2>/dev/null || true
  git clone "${git_repo_url}" .
elif [ -n "${project_archive_b64}" ]; then
  echo "Using embedded deployment archive..."
  echo "${project_archive_b64}" | base64 -d > project.zip
  unzip -oq project.zip
fi

# Dynamic secret resolution: fetch from AWS SSM Parameter Store if present, or generate secure random secret
TOKEN_NAME="/cloud-native-observability/failure-admin-token"
if command -v aws >/dev/null 2>&1 && aws ssm get-parameter --name "$TOKEN_NAME" --with-decryption >/dev/null 2>&1; then
  FAILURE_ADMIN_TOKEN=$(aws ssm get-parameter --name "$TOKEN_NAME" --with-decryption --query "Parameter.Value" --output text)
  echo "Retrieved FAILURE_ADMIN_TOKEN from AWS SSM Parameter Store"
else
  FAILURE_ADMIN_TOKEN=$(openssl rand -hex 32)
  echo "Generated secure random FAILURE_ADMIN_TOKEN"
fi

cat <<EOF > /opt/cloud-native-observability/.env
FAILURE_ADMIN_TOKEN=$FAILURE_ADMIN_TOKEN
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$(openssl rand -hex 16)
EOF
chmod 600 /opt/cloud-native-observability/.env

docker compose up --build -d

for attempt in $(seq 1 60); do
  if curl --fail --silent http://localhost:80/healthz >/dev/null \
    && curl --fail --silent http://localhost:8080/health >/dev/null \
    && curl --fail --silent http://localhost:9090/-/ready >/dev/null \
    && curl --fail --silent http://localhost:9093/-/ready >/dev/null \
    && curl --fail --silent http://localhost:3000/api/health >/dev/null; then
    echo "All application and gateway services are healthy" >> /var/log/cloud-native-observability-status.log
    exit 0
  fi
  sleep 5
done

echo "One or more application services failed health checks" >> /var/log/cloud-native-observability-status.log
docker compose ps >> /var/log/cloud-native-observability-status.log
docker compose logs --tail 100 >> /var/log/cloud-native-observability.log
exit 1
