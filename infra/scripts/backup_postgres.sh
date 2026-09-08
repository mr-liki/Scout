#!/bin/bash
set -euo pipefail

# SCOUTJOBS PostgreSQL Backup Script
# Self-hosted WSL2 deployment
# Primary backup: /mnt/e/ScoutJobsBackups/PostgreSQL

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/mnt/e/ScoutJobsBackups/PostgreSQL}"
SECONDARY_BACKUP_DIR="${SECONDARY_BACKUP_DIR:-}"
TIMESTAMP=$(date -u +%Y%m%dTH%M%SZ)
BACKUP_FILE="${BACKUP_DIR}/scoutjobs-${TIMESTAMP}.dump"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting PostgreSQL backup..."

# Dump database (do not print password)
pg_dump -Fc \
    -U "${POSTGRES_USER:-scoutjobs}" \
    -d "${POSTGRES_DB:-scoutjobs}" \
    -h localhost \
    > "$BACKUP_FILE"

# Verify backup file is non-empty
FILE_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
if [ "$FILE_SIZE" -lt 100 ]; then
    echo "ERROR: Backup file is too small ($FILE_SIZE bytes), likely failed"
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup created: $BACKUP_FILE ($FILE_SIZE bytes)"

# Optional: Copy to secondary backup location
if [ -n "$SECONDARY_BACKUP_DIR" ]; then
    mkdir -p "$SECONDARY_BACKUP_DIR"
    if cp "$BACKUP_FILE" "$SECONDARY_BACKUP_DIR/"; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Secondary backup copy created"
    else
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WARNING: Secondary backup copy failed, primary preserved"
    fi
fi

# Cleanup old local backups
find "$BACKUP_DIR" -name "scoutjobs-*.dump" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup complete. Retention: ${RETENTION_DAYS} days"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Windows path: E:\\ScoutJobsBackups\\PostgreSQL"
