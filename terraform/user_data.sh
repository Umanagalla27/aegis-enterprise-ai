#!/bin/bash
# First-boot setup for the Aegis VM: Docker + the repository. Secrets are NOT baked in:
# create /opt/aegis/docker/.env over SSH (see docs/PRODUCTION_DEPLOYMENT_GUIDE.md, Phase 6).
set -euxo pipefail

apt-get update
apt-get install -y ca-certificates curl git unattended-upgrades
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu
systemctl enable --now docker

git clone https://github.com/Umanagalla27/aegis-enterprise-ai.git /opt/aegis
chown -R ubuntu:ubuntu /opt/aegis
