#!/bin/bash
set -euo pipefail

# SCOUTJOBS Production Status Script
# Shows current state of all services

DEPLOY_DIR="${DEPLOY_DIR:-/opt/scoutjobs}"
ENV_FILE="${DEPLOY_DIR}/infra/.env.production"

echo "========================================="
echo "  SCOUTJOBS Production Status"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "========================================="
echo ""

# Step 1: Docker status
echo "Docker Status:"
if docker info > /dev/null 2>&1; then
    echo "  ✅ Docker Engine: Running"
    echo "     Version: $(docker --version | cut -d' ' -f3 | tr -d ',')"
else
    echo "  ❌ Docker Engine: Not running"
fi
echo ""

# Step 2: Service status
echo "Service Status:"
if [ -f "$ENV_FILE" ]; then
    cd "$DEPLOY_DIR"
    docker compose --env-file "$ENV_FILE" -f infra/docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  Unable to get service status"
else
    echo "  Environment file not found"
fi
echo ""

# Step 3: Health checks
echo "Health Checks:"
# API Health
if docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" 2>/dev/null; then
    echo "  ✅ API: Healthy"
else
    echo "  ❌ API: Unhealthy"
fi

# PostgreSQL
if docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" exec -T postgres pg_isready -U scoutjobs 2>/dev/null | grep -q "accepting connections"; then
    echo "  ✅ PostgreSQL: Accepting connections"
else
    echo "  ❌ PostgreSQL: Not ready"
fi

# Valkey
if docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" exec -T valkey valkey-cli ping 2>/dev/null | grep -q "PONG"; then
    echo "  ✅ Valkey: Responding"
else
    echo "  ❌ Valkey: Not responding"
fi
echo ""

# Step 4: Queue depth
echo "Queue Depth:"
QUEUE_DEPTH=$(docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/infra/docker-compose.prod.yml" exec -T valkey valkey-cli llen "linkedin_search" 2>/dev/null || echo "0")
echo "  LinkedIn search queue: $QUEUE_DEPTH jobs"
echo ""

# Step 5: Disk usage
echo "Disk Usage:"
echo "  WSL Filesystem:"
df -h / | tail -1 | awk '{printf "    Used: %s / %s (%s)\n", $3, $2, $5}'
echo ""

# Step 6: Windows backup location
echo "Windows Backup Location:"
if [ -d "/mnt/e/ScoutJobsBackups" ]; then
    BACKUP_COUNT=$(find /mnt/e/ScoutJobsBackups/PostgreSQL -name "scoutjobs-*.dump" 2>/dev/null | wc -l)
    LATEST_BACKUP=$(ls -t /mnt/e/ScoutJobsBackups/PostgreSQL/scoutjobs-*.dump 2>/dev/null | head -1)
    echo "  ✅ Backup directory exists"
    echo "     Backups: $BACKUP_COUNT"
    if [ -n "$LATEST_BACKUP" ]; then
        echo "     Latest: $(basename $LATEST_BACKUP)"
    fi
else
    echo "  ⚠️  Backup directory not found"
fi
echo ""

# Step 7: Systemd services
echo "Systemd Services:"
if systemctl is-active scoutjobs.service > /dev/null 2>&1; then
    echo "  ✅ scoutjobs.service: Active"
else
    echo "  ⚠️  scoutjobs.service: Inactive"
fi

if systemctl is-active scoutjobs-backup.timer > /dev/null 2>&1; then
    echo "  ✅ scoutjobs-backup.timer: Active"
else
    echo "  ⚠️  scoutjobs-backup.timer: Inactive"
fi
echo ""

# Step 8: Memory
echo "Memory:"
free -h | grep "Mem:" | awk '{printf "  Used: %s / %s\n", $3, $2}'
echo ""

echo "========================================="
