#!/bin/bash
# Run once on a fresh Amazon Linux 2023 EC2 (t2/t3.micro, free tier). Open inbound ports 22 and 80.
set -e
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
echo "Done. Log out/in, then: git clone <your repo> ~/crm && cd ~/crm && cp .env.example .env && nano .env && docker compose up -d --build"
