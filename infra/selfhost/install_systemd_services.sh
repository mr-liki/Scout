#!/bin/bash
set -euo pipefail

# SCOUTJOBS Systemd Service Installer
# Installs systemd services for auto-start and backup

DEPLOY_DIR="${DEPLOY_DIR:-/opt/scoutjobs}"
ENV_FILE="${DEPLOY_DIR}/infra/.env.production"

echo "========================================"
echo "  SCOUTJOBS Systemd Service Installer"
echo "========================================"

# Verify environment file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found"
    exit 1
fi

# Step 1: Create main service
echo ""
echo "Step 1: Creating scoutjobs.service..."
sudo tee /etc/systemd/system/scoutjobs.service > /dev/null << 'EOF'
[Unit]
Description=SCOUTJOBS Production Stack
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/scoutjobs
ExecStart=/usr/bin/docker compose --env-file /opt/scoutjobs/infra/.env.production -f /opt/scoutjobs/infra/docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose --env-file /opt/scoutjobs/infra/.env.production -f /opt/scoutjobs/infra/docker-compose.prod.yml stop
ExecReload=/usr/bin/docker compose --env-file /opt/scoutjobs/infra/.env.production -f /opt/scoutjobs/infra/docker-compose.prod.yml up -d --force-recreate
TimeoutStartSec=300
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF

echo "✅ scoutjobs.service created"

# Step 2: Create backup service
echo ""
echo "Step 2: Creating scoutjobs-backup.service..."
sudo tee /etc/systemd/system/scoutjobs-backup.service > /dev/null << EOF
[Unit]
Description=SCOUTJOBS PostgreSQL Backup
After=docker.service scoutjobs.service
Requires=docker.service

[Service]
Type=oneshot
User=$USER
WorkingDirectory=${DEPLOY_DIR}
ExecStart=/bin/bash -c 'docker compose --env-file ${DEPLOY_DIR}/infra/.env.production -f ${DEPLOY_DIR}/infra/docker-compose.prod.yml exec -T postgres /scripts/backup_postgres.sh'
Environment=BACKUP_DIR=/mnt/e/ScoutJobsBackups/PostgreSQL
Environment=POSTGRES_USER=scoutjobs
Environment=POSTGRES_DB=scoutjobs
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "✅ scoutjobs-backup.service created"

# Step 3: Create backup timer
echo ""
echo "Step 3: Creating scoutjobs-backup.timer..."
sudo tee /etc/systemd/system/scoutjobs-backup.timer > /dev/null << 'EOF'
[Unit]
Description=Run SCOUTJOBS backup daily at 02:00

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

echo "✅ scoutjobs-backup.timer created"

# Step 4: Reload systemd
echo ""
echo "Step 4: Reloading systemd daemon..."
sudo systemctl daemon-reload
echo "✅ Systemd daemon reloaded"

# Step 5: Enable services
echo ""
echo "Step 5: Enabling services..."
sudo systemctl enable scoutjobs.service
sudo systemctl enable scoutjobs-backup.timer
echo "✅ Services enabled"

# Step 6: Verify
echo ""
echo "Step 6: Verifying services..."
echo "scoutjobs.service:"
systemctl list-unit-files | grep scoutjobs
echo ""
echo "scoutjobs-backup.timer:"
systemctl list-timers | grep scoutjobs

echo ""
echo "========================================"
echo "  Systemd Services Installed!"
echo "========================================"
echo ""
echo "Commands:"
echo "  Start:   sudo systemctl start scoutjobs"
echo "  Stop:    sudo systemctl stop scoutjobs"
echo "  Status:  sudo systemctl status scoutjobs"
echo "  Logs:    journalctl -u scoutjobs -f"
echo ""
echo "Backup:"
echo "  Timer status: systemctl list-timers | grep scoutjobs"
echo "  Manual run:   sudo systemctl start scoutjobs-backup.service"
echo "  Logs:         journalctl -u scoutjobs-backup.service"
