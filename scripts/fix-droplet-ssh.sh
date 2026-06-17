#!/usr/bin/env bash
# Run this in the DigitalOcean WEB CONSOLE (Access → Launch Droplet Console)
# when SSH from your Mac times out. Fixes sshd + firewall, then enables SSH.
set -euo pipefail

echo "==> FinFlow SSH recovery script"

export DEBIAN_FRONTEND=noninteractive

# Finish any interrupted package configuration
dpkg --configure -a 2>/dev/null || true

# Ensure SSH server is installed and running
apt-get update -qq
apt-get install -y -qq openssh-server

# Keep existing sshd_config if prompted
apt-get install -y -qq \
  -o Dpkg::Options::="--force-confdef" \
  -o Dpkg::Options::="--force-confold" \
  openssh-server

systemctl enable ssh
systemctl restart ssh
systemctl status ssh --no-pager || true

# Allow SSH through UFW if active
if command -v ufw >/dev/null 2>&1; then
  ufw allow 22/tcp || true
  ufw allow 8088/tcp || true
  ufw status || true
fi

# Show listening ports
ss -tlnp | grep -E ':22|:8088' || true

echo ""
echo "==> SSH service should be running on port 22."
echo "==> From your Mac, test:"
echo "    ssh -i ~/.ssh/digitalocean root@$(curl -sf ifconfig.me || hostname -I | awk '{print $1}')"
echo ""
echo "==> IMPORTANT: In DigitalOcean panel, also check:"
echo "    1. Droplet → Networking → Firewalls → allow inbound TCP 22 and 8088"
echo "    2. Droplet → Power → Power cycle (if SSH still times out)"
