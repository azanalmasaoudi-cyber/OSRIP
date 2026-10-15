#!/bin/sh
# One-time preparation of a fresh Ubuntu 24.04 server for OSRIP (run as root).
# Installs Docker and Compose from Ubuntu's own packages, opens only SSH, HTTP and
# HTTPS in the firewall, and adds swap on small machines (the web image build needs it).
set -eu
export DEBIAN_FRONTEND=noninteractive

apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 ufw
systemctl enable --now docker

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

mem_mb=$(free -m | awk '/^Mem:/ {print $2}')
if [ ! -f /swapfile ] && [ "$mem_mb" -lt 3500 ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

mkdir -p /opt/osrip/src
docker --version
docker compose version
echo "server ready"
