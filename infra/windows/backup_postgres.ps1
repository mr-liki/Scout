<# 
.SYNOPSIS
    Backup SCOUTJOBS PostgreSQL database via Docker.
.DESCRIPTION
    Creates a pg_dump -Fc backup inside the running postgres container,
    copies it to the Windows host, and rotates old backups.
.PARAMETER BackupDir
    Target directory on the Windows host. Default: E:\ScoutJobsBackups\PostgreSQL
.PARAMETER RetentionDays
    Number of days to keep old backups. Default: 14
.NOTES
    Run from E:\Scout directory or pass -ProjectRoot.
#>
param(
    [string]$BackupDir = "E:\ScoutJobsBackups\PostgreSQL",
    [int]$RetentionDays = 14,
    [string]$ProjectRoot = "E:\Scout"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Validate prerequisites ──────────────────────────────────────
if (-not (Test-Path "$ProjectRoot\infra\docker-compose.prod.yml")) {
    Write-Error "docker-compose.prod.yml not found at $ProjectRoot\infra"
    exit 1
}

$envFile = "$ProjectRoot\infra\.env.production"
if (-not (Test-Path $envFile)) {
    Write-Error "Production .env file not found at $envFile"
    exit 1
}

# ── Create backup directory ─────────────────────────────────────
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    Write-Host "[OK] Created backup directory: $BackupDir"
}

# ── Generate backup filename ────────────────────────────────────
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$dumpFile = "scoutjobs-$timestamp.dump"
$containerPath = "/tmp/$dumpFile"
$localPath = "$BackupDir\$dumpFile"

if (Test-Path $localPath) {
    Write-Error "Backup file already exists, refusing to overwrite: $localPath"
    exit 1
}

Write-Host "[INFO] Starting PostgreSQL backup..."
Write-Host "       File: $localPath"

# ── Run pg_dump inside container ────────────────────────────────
Push-Location $ProjectRoot
try {
    $composeCmd = "docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml"
    
    # Create the dump inside the container
    $dumpCmd = "$composeCmd exec -T postgres pg_dump -U scoutjobs -d scoutjobs -Fc -f $containerPath"
    Write-Host "[INFO] Running pg_dump..."
    Invoke-Expression $dumpCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pg_dump failed with exit code $LASTEXITCODE"
        exit 1
    }

    # Copy dump from container to host
    Write-Host "[INFO] Copying dump to host..."
    $copyCmd = "$composeCmd cp postgres:$containerPath $localPath"
    Invoke-Expression $copyCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Container cp failed with exit code $LASTEXITCODE"
        exit 1
    }

    # Cleanup container temp file
    $cleanupCmd = "$composeCmd exec -T postgres rm -f $containerPath"
    Invoke-Expression $cleanupCmd | Out-Null

    # Validate backup file
    $fileInfo = Get-Item $localPath
    if ($fileInfo.Length -eq 0) {
        Write-Error "Backup file is empty: $localPath"
        exit 1
    }

    $sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)
    Write-Host "[OK] Backup created successfully"
    Write-Host "     Size: ${sizeMB} MB"
    Write-Host "     Path: $localPath"

    # ── Rotate old backups ──────────────────────────────────────
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $oldBackups = @(Get-ChildItem -Path $BackupDir -Filter "scoutjobs-*.dump" -File |
        Where-Object { $_.LastWriteTime -lt $cutoff })

    if ($oldBackups.Count -gt 0) {
        Write-Host "[INFO] Rotating $($oldBackups.Count) backup(s) older than $RetentionDays days..."
        foreach ($old in $oldBackups) {
            Remove-Item $old.FullName -Force
            Write-Host "       Removed: $($old.Name)"
        }
    }

    Write-Host "[DONE] Backup complete."
}
finally {
    Pop-Location
}
