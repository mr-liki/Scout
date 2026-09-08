<#
.SYNOPSIS
    Show SCOUTJOBS Docker stack status.
.DESCRIPTION
    Displays container health, service status, tunnel status, volumes,
    latest backup, and basic diagnostics. Never prints secrets.
.PARAMETER ProjectRoot
    Path to the project root. Default: resolved from this script's own location.
#>
param(
    [string]$ProjectRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$envFile = "$ProjectRoot\infra\.env.production"
$composeFile = "$ProjectRoot\infra\docker-compose.prod.yml"
$composeBase = "docker compose --env-file `"$envFile`" -f `"$composeFile`""
$backupDir = "E:\ScoutJobsBackups\PostgreSQL"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SCOUTJOBS Backend Status" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Docker Engine ───────────────────────────────────────────────
Write-Host "Docker Engine:" -ForegroundColor Yellow
docker info 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Running" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Unavailable" -ForegroundColor Red
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    exit 1
}

# ── Container Status ────────────────────────────────────────────
Write-Host ""
Write-Host "Containers:" -ForegroundColor Yellow
Invoke-Expression "$composeBase ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'"
Write-Host ""

# ── PostgreSQL ──────────────────────────────────────────────────
Write-Host "PostgreSQL:" -ForegroundColor Yellow
try {
    $pgResult = Invoke-Expression "$composeBase exec -T postgres pg_isready -U scoutjobs 2>&1"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Ready" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Not ready" -ForegroundColor Red
    }
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
}

# ── Valkey ──────────────────────────────────────────────────────
Write-Host "Valkey:" -ForegroundColor Yellow
try {
    $valResult = Invoke-Expression "$composeBase exec -T valkey valkey-cli PING 2>&1"
    if ($valResult -match "PONG") {
        Write-Host "  [OK] PONG" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $valResult" -ForegroundColor Red
    }
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
}

# ── API Health ──────────────────────────────────────────────────
Write-Host "API:" -ForegroundColor Yellow
try {
    $apiResult = Invoke-Expression "$composeBase exec -T api python -c `"import urllib.request; r=urllib.request.urlopen('http://localhost:8000/healthz'); print(r.read().decode())`" 2>&1"
    if ($apiResult -match '"status":\s*"ok"') {
        Write-Host "  [OK] healthz responding" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $apiResult" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
}

# ── Readiness ───────────────────────────────────────────────────
Write-Host "Readiness:" -ForegroundColor Yellow
try {
    $readyResult = Invoke-Expression "$composeBase exec -T api python -c `"import urllib.request; r=urllib.request.urlopen('http://localhost:8000/readyz'); print(r.read().decode())`" 2>&1"
    if ($readyResult -match '"status":\s*"ready"') {
        Write-Host "  [OK] database=ok cache=ok" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $readyResult" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
}

# ── LinkedIn Worker Count ───────────────────────────────────────
Write-Host "LinkedIn Worker:" -ForegroundColor Yellow
try {
    $workerIds = @(Invoke-Expression "$composeBase ps -q linkedin_worker")
    $workerCount = $workerIds.Count
    if ($workerCount -eq 1) {
        Write-Host "  [OK] Exactly 1 worker running" -ForegroundColor Green
    } elseif ($workerCount -eq 0) {
        Write-Host "  [FAIL] No worker running" -ForegroundColor Red
    } else {
        Write-Host "  [WARN] $workerCount workers running (expected exactly 1)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
}

# ── RQ Queue Depth ──────────────────────────────────────────────
Write-Host "RQ Queue:" -ForegroundColor Yellow
try {
    $qLen = Invoke-Expression "$composeBase exec -T valkey valkey-cli LLEN rq:queue:linkedin_search 2>&1"
    Write-Host "  Pending jobs: $qLen"
} catch {
    Write-Host "  [WARN] Could not check queue" -ForegroundColor Yellow
}

# ── Cloudflare Tunnel ───────────────────────────────────────────
Write-Host ""
Write-Host "Cloudflare Tunnel:" -ForegroundColor Yellow
$tokenConfigured = $false
if (Test-Path $envFile) {
    $tokenConfigured = [bool](Select-String -Path $envFile -Pattern "^CLOUDFLARE_TUNNEL_TOKEN=.+" -Quiet)
}
$namedTunnelRunning = $false
try {
    $namedPs = Invoke-Expression "$composeBase --profile tunnel ps -q cloudflared" 2>$null
    $namedTunnelRunning = [bool]$namedPs
} catch { }

$quickTunnelRunning = $false
try {
    $quickPs = Invoke-Expression "$composeBase --profile quick-tunnel ps -q cloudflared-quick" 2>$null
    $quickTunnelRunning = [bool]$quickPs
} catch { }

if ($namedTunnelRunning) {
    Write-Host "  [RUNNING] Named tunnel (production)" -ForegroundColor Green
} elseif ($quickTunnelRunning) {
    Write-Host "  [RUNNING] Quick Tunnel (TESTING ONLY, temporary URL)" -ForegroundColor Yellow
    Write-Host "  Run: docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml --profile quick-tunnel logs cloudflared-quick"
    Write-Host "  to see the current https://xxxx.trycloudflare.com URL."
} elseif ($tokenConfigured) {
    Write-Host "  [STOPPED] Named tunnel token configured but tunnel is not running" -ForegroundColor Yellow
} else {
    Write-Host "  [NOT CONFIGURED] No tunnel token set; Quick Tunnel not running" -ForegroundColor Yellow
}

# ── Volumes ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "Volumes:" -ForegroundColor Yellow
$pgVolume = docker volume ls -q --filter "name=infra_postgres_data"
$valkeyVolume = docker volume ls -q --filter "name=infra_valkey_data"
if ($pgVolume) {
    Write-Host "  [OK] infra_postgres_data present" -ForegroundColor Green
} else {
    Write-Host "  [MISSING] infra_postgres_data" -ForegroundColor Red
}
if ($valkeyVolume) {
    Write-Host "  [OK] infra_valkey_data present" -ForegroundColor Green
} else {
    Write-Host "  [MISSING] infra_valkey_data" -ForegroundColor Red
}

# ── Latest Backup ───────────────────────────────────────────────
Write-Host ""
Write-Host "Latest Backup:" -ForegroundColor Yellow
if (Test-Path $backupDir) {
    $latest = Get-ChildItem -Path $backupDir -Filter "scoutjobs-*.dump" -File |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) {
        $ageHours = [math]::Round(((Get-Date) - $latest.LastWriteTime).TotalHours, 1)
        $sizeMB = [math]::Round($latest.Length / 1MB, 2)
        Write-Host "  File: $($latest.Name)"
        Write-Host "  Age:  $ageHours hours"
        Write-Host "  Size: $sizeMB MB"
    } else {
        Write-Host "  [WARN] No backups found in $backupDir" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [WARN] Backup directory does not exist: $backupDir" -ForegroundColor Yellow
}

# ── Docker Disk Usage ───────────────────────────────────────────
Write-Host ""
Write-Host "Docker Disk:" -ForegroundColor Yellow
docker system df 2>$null | Select-Object -Last 4

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
