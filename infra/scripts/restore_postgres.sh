#!/bin/bash
set -euo pipefail

# SCOUTJOBS PostgreSQL Restore Script
# WARNING: This will DROP and recreate the database!
# Usage: ./restore_postgres.sh <backup_file>

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <backup_file>"
    echo ""
    echo "Available backups:"
    ls -la "$BACKUP_DIR"/scoutjobs-*.dump 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Verify file is a valid dump (check first bytes)
FILE_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
if [ "$FILE_SIZE" -lt 100 ]; then
    echo "ERROR: Backup file is too small ($FILE_SIZE bytes), likely invalid"
    exit 1
fi

echo "========================================="
echo "  SCOUTJOBS DATABASE RESTORE"
echo "========================================="
echo ""
echo "WARNING: This will DROP and recreate the database!"
echo ""
echo "Backup file: $BACKUP_FILE"
echo "File size:   $FILE_SIZE bytes"
echo ""
echo "Database:    ${POSTGRES_DB:-scoutjobs}"
echo "User:        ${POSTGRES_USER:-scoutjobs}"
echo ""

# Require explicit confirmation
read -p "Type 'RESTORE' to confirm: " CONFIRM
if [ "$CONFIRM" != "RESTORE" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Dropping existing database..."
dropdb -U "${POSTGRES_USER:-scoutjobs}" --if-exists "${POSTGRES_DB:-scoutjobs}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Creating fresh database..."
createdb -U "${POSTGRES_USER:-scoutjobs}" "${POSTGRES_DB:-scoutjobs}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restoring from backup..."
pg_restore -Fc \
    -U "${POSTGRES_USER:-scoutjobs}" \
    -d "${POSTGRES_DB:-scoutjobs}" \
    "$BACKUP_FILE"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restore complete!"
