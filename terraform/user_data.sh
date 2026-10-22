#!/bin/bash
# First-boot setup for the Aegis VM: Docker + the repository. Secrets are NOT baked in:
# create /opt/aegis/docker/.env over SSH (see docs/PRODUCTION_DEPLOYMENT_GUIDE.md, Phase 6).
set -euxo pipefail

# The instance has no auto-assigned public IP; outbound access starts once Terraform
# attaches the Elastic IP, a few seconds after boot. Wait for it (up to 10 minutes).
for _ in $(seq 1 120); do
  curl -fsS --proto '=https' --tlsv1.2 -o /dev/null https://get.docker.com && break
  sleep 5
done

apt-get update
apt-get install -y ca-certificates curl git unattended-upgrades
# HTTPS only, also for redirects (--proto), so the installer cannot be downgraded to HTTP
curl -fsSL --proto '=https' --tlsv1.2 https://get.docker.com -o /tmp/get-docker.sh
sh /tmp/get-docker.sh
usermod -aG docker ubuntu
systemctl enable --now docker

git clone https://github.com/Umanagalla27/aegis-enterprise-ai.git /opt/aegis
chown -R ubuntu:ubuntu /opt/aegis
