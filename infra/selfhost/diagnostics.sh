#!/bin/bash
set -euo pipefail

# SCOUTJOBS Production Diagnostics Script
# Collects safe diagnostic information
# NEVER outputs secrets or credentials

DEPLOY_DIR="${DEPLOY_DIR:-/opt/scoutjobs}"
ENV_FILE="${DEPLOY_DIR}/infra/.env.production"

echo "========================================="
echo "  SCOUTJOBS Production Diagnostics"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "========================================="
echo ""

# System Information
echo "System Information:"
echo "  OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
echo "  Kernel: $(uname -r)"
echo "  Architecture: $(uname -m)"
echo "  Hostname: $(hostname)"
echo ""

# Memory
echo "Memory:"
free -h
echo ""

# Disk
echo "Disk Usage:"
df -h / 2>/dev/null
echo ""

# Docker
echo "Docker Information:"
if docker info > /dev/null 2>&1; then
    echo "  Docker Version: $(docker --version)"
    echo "  Docker Compose: $(docker compose version)"
    echo "  Running Containers: $(docker ps -q | wc -l)"
    echo "  Total Images: $(docker images -q | wc -l)"
    echo ""
    echo "  Docker Disk Usage:"
    docker system df 2>/dev/null || echo "  Unable to get disk usage"
else
    echo "  Docker not running"
fi
echo ""

# Service Status
echo "Service Status:"
if [ -f "$ENV_FILE" ]; then
    cd "$DEPLOY_DIR"
    docker compose --env-file "$ENV_FILE" -f infra/docker-compose.prod.yml ps 2>/dev/null || echo "  Unable to get status"
else
    echo "  Environment file not found"
fi
echo ""

# Recent Logs (sanitized)
echo "Recent API Logs (last 10 lines):"
docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" logs --tail=10 api 2>/dev/null | grep -v "password" | grep -v "PASSWORD" | grep -v "token" | grep -v "TOKEN" || echo "  Unable to get logs"
echo ""

echo "Recent Worker Logs (last 10 lines):"
docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" logs --tail=10 linkedin_worker 2>/dev/null | grep -v "password" | grep -v "PASSWORD" | grep -v "token" | grep -v "TOKEN" || echo "  Unable to get logs"
echo ""

# Health States
echo "Health States:"
if docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" 2>/dev/null; then
    echo "  API: Healthy"
else
    echo "  API: Unhealthy"
fi

if docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" exec -T postgres pg_isready -U scoutjobs 2>/dev/null | grep -q "accepting connections"; then
    echo "  PostgreSQL: Ready"
else
    echo "  PostgreSQL: Not ready"
fi

if docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" exec -T valkey valkey-cli ping 2>/dev/null | grep -q "PONG"; then
    echo "  Valkey: Responding"
else
    echo "  Valkey: Not responding"
fi
echo ""

# Systemd
echo "Systemd Services:"
systemctl status scoutjobs.service --no-pager 2>/dev/null | head -5 || echo "  scoutjobs.service not found"
echo ""
systemctl status scoutjobs-backup.timer --no-pager 2>/dev/null | head -5 || echo "  scoutjobs-backup.timer not found"
echo ""

echo "========================================="
echo "  Diagnostics Complete"
echo "========================================="
