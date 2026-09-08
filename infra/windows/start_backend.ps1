<#
.SYNOPSIS
    Start the SCOUTJOBS production Docker stack.
.DESCRIPTION
    Waits for Docker Desktop engine, applies pending database migrations,
    then starts postgres, valkey, api, and linkedin_worker.
    Optionally starts cloudflared if a tunnel token is configured.
.PARAMETER ProjectRoot
    Path to the project root. Default: resolved from this script's own location,
    so the script works regardless of the caller's current directory.
.PARAMETER IncludeTunnel
    If specified, also starts the named cloudflared tunnel service (requires
    CLOUDFLARE_TUNNEL_TOKEN to be configured).
.PARAMETER IncludeQuickTunnel
    If specified, also starts a free, temporary Quick Tunnel
    (https://xxxx.trycloudflare.com). No token required. Development/testing
    only -- see docs/QUICK_TUNNEL_TESTING.md. Mutually exclusive with
    -IncludeTunnel.
#>
param(
    [string]$ProjectRoot,
    [switch]$IncludeTunnel,
    [switch]$IncludeQuickTunnel
)

if ($IncludeTunnel -and $IncludeQuickTunnel) {
    Write-Error "-IncludeTunnel and -IncludeQuickTunnel are mutually exclusive. Pick one."
    exit 1
}

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$composeFile = "$ProjectRoot\infra\docker-compose.prod.yml"
$envFile = "$ProjectRoot\infra\.env.production"
$composeCmd = "docker compose --env-file `"$envFile`" -f `"$composeFile`""

# ── Validate prerequisites ──────────────────────────────────────
if (-not (Test-Path $composeFile)) {
    Write-Error "docker-compose.prod.yml not found at $ProjectRoot\infra"
    exit 1
}
if (-not (Test-Path $envFile)) {
    Write-Error ".env.production not found at $ProjectRoot\infra"
    exit 1
}

# ── Wait for Docker Desktop engine (every 5s, up to ~2 minutes) ──
Write-Host "[INFO] Waiting for Docker engine..."
$retryIntervalSeconds = 5
$maxWaitSeconds = 120
$waited = 0
$dockerReady = $false
while ($waited -lt $maxWaitSeconds) {
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Docker engine is ready" -ForegroundColor Green
        $dockerReady = $true
        break
    }
    Start-Sleep -Seconds $retryIntervalSeconds
    $waited += $retryIntervalSeconds
    Write-Host "  Waiting... (${waited}s)"
}
if (-not $dockerReady) {
    Write-Error "Docker engine not available after ${maxWaitSeconds}s"
    exit 1
}

# ── Start core data services and wait for health ─────────────────
Write-Host ""
Write-Host "[INFO] Starting postgres and valkey..."
Invoke-Expression "$composeCmd up -d --wait postgres valkey"

# ── Apply pending database migrations ─────────────────────────────
Write-Host "[INFO] Applying database migrations..."
Invoke-Expression "$composeCmd run --rm --no-deps api python -m alembic -c backend/db/alembic.ini upgrade head"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Database migration failed (exit code $LASTEXITCODE). Aborting startup."
    exit 1
}
Write-Host "[OK] Migrations applied" -ForegroundColor Green

# ── Start API and worker, wait for health ─────────────────────────
Write-Host "[INFO] Starting API and LinkedIn worker..."
Invoke-Expression "$composeCmd up -d --wait api linkedin_worker"

$workerCount = (Invoke-Expression "$composeCmd ps -q linkedin_worker" | Measure-Object).Count
if ($workerCount -eq 1) {
    Write-Host "[OK] Exactly one LinkedIn worker running" -ForegroundColor Green
} else {
    Write-Host "[WARN] Expected exactly 1 linkedin_worker container, found $workerCount" -ForegroundColor Yellow
}

# ── Optional: start cloudflared (named tunnel) ────────────────────
if ($IncludeTunnel) {
    $tokenPresent = Select-String -Path $envFile -Pattern "^CLOUDFLARE_TUNNEL_TOKEN=.+" -Quiet
    if ($tokenPresent) {
        Write-Host "[INFO] Starting cloudflared tunnel..."
        Invoke-Expression "$composeCmd --profile tunnel up -d cloudflared"
    } else {
        Write-Host "[SKIP] Cloudflare Tunnel token is not configured." -ForegroundColor Yellow
        Write-Host "       Core SCOUTJOBS backend remains running." -ForegroundColor Yellow
    }
}

# ── Optional: start cloudflared (free Quick Tunnel, testing only) ─
if ($IncludeQuickTunnel) {
    Write-Host "[INFO] Starting Quick Tunnel (no token required)..."
    Invoke-Expression "$composeCmd --profile quick-tunnel up -d cloudflared-quick"

    Write-Host "[INFO] Waiting for the trycloudflare.com URL to appear in logs..."
    $tunnelUrl = $null
    $urlWaitSeconds = 0
    while (-not $tunnelUrl -and $urlWaitSeconds -lt 30) {
        $logLine = Invoke-Expression "$composeCmd --profile quick-tunnel logs cloudflared-quick" |
            Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com"
        if ($logLine) {
            $tunnelUrl = $logLine.Matches[0].Value
        } else {
            Start-Sleep -Seconds 3
            $urlWaitSeconds += 3
        }
    }

    if ($tunnelUrl) {
        Write-Host "[OK] Quick Tunnel URL: $tunnelUrl" -ForegroundColor Green
        Write-Host "[NOTE] This URL is TEMPORARY (testing only) -- see docs/QUICK_TUNNEL_TESTING.md." -ForegroundColor Yellow

        $syncScript = Join-Path $ProjectRoot "infra\windows\sync_worker_backend_url.py"
        $hasCfCreds = (Select-String -Path $envFile -Pattern "^CLOUDFLARE_API_TOKEN=.+" -Quiet) -and
                      (Select-String -Path $envFile -Pattern "^CLOUDFLARE_ACCOUNT_ID=.+" -Quiet)
        if ($hasCfCreds) {
            Write-Host "[INFO] Syncing BACKEND_API_URL to the Cloudflare Worker..."
            python "$syncScript" "$tunnelUrl"
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[WARN] Worker sync failed -- scout.apexora.workers.dev/api/* may still point at an old URL." -ForegroundColor Yellow
                Write-Host "       See docs/QUICK_TUNNEL_TESTING.md to update it manually." -ForegroundColor Yellow
            }
        } else {
            Write-Host "[SKIP] CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID not configured -- Worker not auto-synced." -ForegroundColor Yellow
            Write-Host "       Update BACKEND_API_URL manually, or see docs/QUICK_TUNNEL_TESTING.md to enable auto-sync." -ForegroundColor Yellow
        }
    } else {
        Write-Host "[WARN] Could not read the Quick Tunnel URL from logs after ${urlWaitSeconds}s." -ForegroundColor Yellow
    }
}

# ── Verify ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "[INFO] Service status:"
Invoke-Expression "$composeCmd ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'"

Write-Host ""
Write-Host "[DONE] SCOUTJOBS backend started." -ForegroundColor Green
