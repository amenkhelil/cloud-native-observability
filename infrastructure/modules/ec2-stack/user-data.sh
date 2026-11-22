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

docker compose up --build -d

for attempt in $(seq 1 60); do
  if curl --fail --silent http://localhost:8080/health >/dev/null \
    && curl --fail --silent http://localhost:8081/health >/dev/null \
    && curl --fail --silent http://localhost:9090/-/ready >/dev/null \
    && curl --fail --silent http://localhost:9093/-/ready >/dev/null \
    && curl --fail --silent http://localhost:3000/api/health >/dev/null; then
    echo "All application services are healthy" >> /var/log/cloud-native-observability-status.log
    exit 0
  fi
  sleep 5
done

echo "One or more application services failed health checks" >> /var/log/cloud-native-observability-status.log
docker compose ps >> /var/log/cloud-native-observability-status.log
docker compose logs --tail 100 >> /var/log/cloud-native-observability.log
exit 1

