#!/bin/bash
set -euo pipefail

# SCOUTJOBS WSL2 Setup Script
# Run inside WSL2 Ubuntu after installation
# This script is idempotent - safe to run multiple times

echo "========================================"
echo "  SCOUTJOBS WSL2 Setup"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "========================================"

# Step 1: System updates
echo ""
echo "Step 1: Updating system packages..."
sudo apt update -qq
sudo apt upgrade -y -qq

# Step 2: Install required packages
echo ""
echo "Step 2: Installing required packages..."
sudo apt install -y -qq \
    ca-certificates \
    curl \
    git \
    jq \
    gnupg \
    lsb-release \
    apt-transport-https \
    software-properties-common

# Step 3: Verify Docker is installed
echo ""
echo "Step 3: Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing Docker Engine..."
    
    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Add the repository to Apt sources
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker Engine
    sudo apt update -qq
    sudo apt install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin
    
    echo "✅ Docker Engine installed"
else
    echo "✅ Docker already installed: $(docker --version)"
fi

# Step 4: Add user to docker group
echo ""
echo "Step 4: Configuring Docker access..."
if groups "$USER" | grep -q docker; then
    echo "✅ User already in docker group"
else
    sudo usermod -aG docker "$USER"
    echo "⚠️  Added user to docker group. Log out and back in for changes to take effect."
fi

# Step 5: Verify Docker
echo ""
echo "Step 5: Verifying Docker..."
if docker info > /dev/null 2>&1; then
    echo "✅ Docker is running"
    echo "   Docker version: $(docker --version)"
    echo "   Docker Compose: $(docker compose version)"
else
    echo "⚠️  Docker is not running. Start with: sudo systemctl start docker"
fi

# Step 6: Create production directories
echo ""
echo "Step 6: Creating production directories..."
sudo mkdir -p /opt/scoutjobs
sudo mkdir -p /var/log/scoutjobs
sudo chown -R "$USER:docker" /opt/scoutjobs 2>/dev/null || true
sudo chown -R "$USER:docker" /var/log/scoutjobs 2>/dev/null || true

# Step 7: Verify WSL2 storage
echo ""
echo "Step 7: Verifying WSL2 storage..."
echo "   Filesystem type: $(df -T / | tail -1 | awk '{print $2}')"
echo "   Available space: $(df -h / | tail -1 | awk '{print $4}')"

# Step 8: Check systemd
echo ""
echo "Step 8: Checking systemd support..."
if systemctl --version > /dev/null 2>&1; then
    echo "✅ systemd is available"
    systemctl --version | head -1
else
    echo "⚠️  systemd not available. Enable in /etc/wsl.conf:"
    echo "   [boot]"
    echo "   systemd=true"
    echo "   Then restart WSL: wsl --shutdown"
fi

echo ""
echo "========================================"
echo "  WSL2 Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Clone repository: git clone <YOUR_REPO_URL> /opt/scoutjobs"
echo "2. Configure environment: cp /opt/scoutjobs/infra/.env.production.example /opt/scoutjobs/infra/.env.production"
echo "3. Edit environment: nano /opt/scoutjobs/infra/.env.production"
echo "4. Deploy: cd /opt/scoutjobs && ./infra/scripts/deploy.sh"
