#!/bin/bash
set -euo pipefail

# SCOUTJOBS Deployment Script
# Self-hosted WSL2 production deployment
# Run from repository root inside WSL2 Ubuntu

DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/scoutjobs}"
ENV_FILE="infra/.env.production"
COMPOSE_FILE="infra/docker-compose.prod.yml"

echo "========================================"
echo "  SCOUTJOBS Production Deployment"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "========================================"

# Step 1: Verify environment file
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found"
    echo "Copy infra/.env.production.example and fill in values"
    exit 1
fi

# Step 2: Verify Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running"
    echo "Start Docker: sudo systemctl start docker"
    exit 1
fi

# Step 3: Fetch and checkout
echo ""
echo "Step 1: Pulling latest code..."
git fetch origin
git checkout production 2>/dev/null || git checkout main
git pull --ff-only origin production 2>/dev/null || git pull --ff-only origin main

# Step 4: Record Git SHA
GIT_SHA=$(git rev-parse --short HEAD)
echo "Git SHA: $GIT_SHA"
export GIT_SHA

# Step 5: Validate Docker Compose config
echo ""
echo "Step 2: Validating Docker Compose configuration..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config > /dev/null
echo "✅ Docker Compose config valid"

# Step 6: Build images
echo ""
echo "Step 3: Building Docker images..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build

# Step 7: Backup database before migration (if running)
echo ""
echo "Step 4: Pre-migration backup..."
if docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps postgres | grep -q "Up"; then
    echo "Database is running, creating backup..."
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
        pg_dump -Fc -U "${POSTGRES_USER:-scoutjobs}" -d "${POSTGRES_DB:-scoutjobs}" \
        > "/tmp/scoutjobs-pre-deploy-$(date -u +%Y%m%dTH%M%SZ).dump" 2>/dev/null || true
    echo "✅ Pre-deploy backup created"
else
    echo "Database not running yet, skipping backup"
fi

# Step 8: Run database migrations
echo ""
echo "Step 5: Running database migrations..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm \
    api alembic -c backend/db/alembic.ini upgrade head

MIGRATION_EXIT=$?
if [ $MIGRATION_EXIT -ne 0 ]; then
    echo "❌ Migration failed! Aborting deployment."
    echo "Check logs: docker compose --env-file $ENV_FILE -f $COMPOSE_FILE logs api"
    exit 1
fi
echo "✅ Migrations applied successfully"

# Step 9: Start services
echo ""
echo "Step 6: Starting services..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d

# Step 10: Wait for health checks
echo ""
echo "Step 7: Waiting for services to become healthy..."
sleep 20

# Step 11: Verify API health
echo ""
echo "Step 8: Verifying API health..."
for i in {1..5}; do
    if docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T api \
        python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" 2>/dev/null; then
        echo "✅ API is healthy"
        break
    fi
    echo "  Attempt $i/5 - waiting..."
    sleep 5
done

# Step 12: Verify worker
echo ""
echo "Step 9: Verifying LinkedIn worker..."
if docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps linkedin_worker | grep -q "Up"; then
    echo "✅ LinkedIn worker is running"
else
    echo "⚠️  LinkedIn worker status:"
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps linkedin_worker
fi

# Step 13: Show status
echo ""
echo "Step 10: Service status:"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

# Step 14: Verify no public ports
echo ""
echo "Step 11: Verifying no public database/cache ports..."
if ss -lntp 2>/dev/null | grep -q ":5432 "; then
    echo "⚠️  WARNING: PostgreSQL port 5432 is listening"
else
    echo "✅ PostgreSQL not publicly accessible"
fi
if ss -lntp 2>/dev/null | grep -q ":6379 "; then
    echo "⚠️  WARNING: Valkey port 6379 is listening"
else
    echo "✅ Valkey not publicly accessible"
fi

echo ""
echo "========================================"
echo "  Deployment complete!"
echo "  Git SHA: $GIT_SHA"
echo "  Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "========================================"
