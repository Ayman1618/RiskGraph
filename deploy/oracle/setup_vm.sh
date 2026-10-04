#!/usr/bin/env bash
# ==============================================================================
# RiskGraph Platform — Oracle Cloud VM Host Setup Script
# Target: Oracle Cloud Infrastructure (OCI) Ampere A1 Flex (ARM64)
# OS: Ubuntu 22.04 / 24.04 LTS or Oracle Linux 8 / 9
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [ "$EUID" -ne 0 ]; then
  log_error "Please run this script with sudo: sudo bash setup_vm.sh"
  exit 1
fi

log_info "Starting Oracle Cloud VM provisioning for RiskGraph..."

# 1. Detect Distribution
OS="unknown"
if [ -f /etc/os-release ]; then
  . /etc/os-release
  OS=$ID
fi
log_info "Detected OS: $OS"

# 2. Update System Packages & Install Dependencies
log_info "Updating system packages and installing prerequisites..."
if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
  apt-get update -y
  apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    jq \
    ufw \
    iptables-persistent
elif [ "$OS" = "ol" ] || [ "$OS" = "rhel" ] || [ "$OS" = "centos" ]; then
  dnf update -y
  dnf install -y curl git jq iptables
fi

# 3. Configure OS Kernel Parameters for Databases & Kafka
log_info "Optimizing kernel sysctl settings (vm.max_map_count, file limits)..."
cat << 'EOF' > /etc/sysctl.d/99-riskgraph.conf
# Required for Neo4j memory-mapped I/O and high concurrency
vm.max_map_count=262144
fs.file-max=65536
net.core.somaxconn=1024
EOF
sysctl --system > /dev/null

# 3b. Configure 4 GB NVMe Swap Space (Prevents OOM spikes on 12 GB RAM)
if [ ! -f /swapfile ] && [ "$(swapon --show | wc -l)" -le 1 ]; then
  log_info "Creating 4 GB swap file on NVMe boot volume for memory safety..."
  fallocate -l 4G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  if ! grep -q "/swapfile" /etc/fstab; then
    echo "/swapfile none swap sw 0 0" >> /etc/fstab
  fi
  sysctl vm.swappiness=10 > /dev/null
  echo "vm.swappiness=10" >> /etc/sysctl.d/99-riskgraph.conf
  log_success "4 GB swap file created and activated."
else
  log_info "Swap is already configured ($(free -h 2>/dev/null | awk '/Swap:/ {print $2}' || echo 'active'))."
fi

# 4. Install Docker Engine and Compose Plugin
if ! command -v docker &> /dev/null; then
  log_info "Installing Docker Engine & Docker Compose Plugin..."
  curl -fsSL https://get.docker.com -o get-docker.sh
  sh get-docker.sh
  rm -f get-docker.sh
  systemctl enable docker
  systemctl start docker
  log_success "Docker installed successfully."
else
  log_info "Docker is already installed ($(docker --version))."
fi

# Add real user to docker group if running under sudo
TARGET_USER="${SUDO_USER:-$USER}"
if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ]; then
  usermod -aG docker "$TARGET_USER"
  log_info "Added user '$TARGET_USER' to docker group."
fi

# 5. Open Host Firewall Ports (80, 443, 22)
# NOTE: Oracle Cloud images apply restrictive OS-level iptables rules by default!
# Opening VCN Security List is not enough; host iptables must also allow traffic.
log_info "Configuring OS firewall for ports 80 (HTTP) and 443 (HTTPS)..."

if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
  # Allow in iptables directly (OCI Ubuntu images have default INPUT reject)
  iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
  iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
  netfilter-persistent save 2>/dev/null || true
  
  if command -v ufw &> /dev/null && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 22/tcp
    ufw reload
  fi
elif [ "$OS" = "ol" ] || [ "$OS" = "rhel" ]; then
  if command -v firewall-cmd &> /dev/null && systemctl is-active --quiet firewalld; then
    firewall-cmd --zone=public --permanent --add-port=80/tcp
    firewall-cmd --zone=public --permanent --add-port=443/tcp
    firewall-cmd --reload
  else
    iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
    iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
  fi
fi
log_success "Firewall configured: Ports 80 and 443 are open."

# 6. Summary
log_success "=================================================="
log_success "Oracle Cloud VM Setup Complete!"
log_success "Docker version: $(docker --version)"
log_success "Compose version: $(docker compose version)"
log_success "=================================================="
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. If you just added your user to the docker group, log out and log back in, or run:"
echo "   newgrp docker"
echo "2. Navigate to your RiskGraph directory:"
echo "   cd ~/RiskGraph"
echo "3. Copy the production environment template:"
echo "   cp .env.production.example .env.production"
echo "4. Deploy the complete platform:"
echo "   bash deploy/oracle/deploy.sh"
