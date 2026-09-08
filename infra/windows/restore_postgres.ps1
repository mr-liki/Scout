<#
.SYNOPSIS
    Restore SCOUTJOBS PostgreSQL database from a backup dump.
.DESCRIPTION
    Restores a pg_dump -Fc backup into the running PostgreSQL container.
    Requires explicit -Confirm switch to proceed.
.PARAMETER BackupPath
    Full path to the .dump file to restore.
.PARAMETER Confirm
    Must be "RESTORE" to proceed with the destructive restore.
.PARAMETER ProjectRoot
    Path to the project root. Default: E:\Scout
.EXAMPLE
    .\restore_postgres.ps1 -BackupPath "E:\ScoutJobsBackups\PostgreSQL\scoutjobs-20260907T000000Z.dump" -Confirm RESTORE
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$BackupPath,
    
    [Parameter(Mandatory=$true)]
    [ValidateSet("RESTORE")]
    [string]$Confirm,
    
    [string]$ProjectRoot = "E:\Scout"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Validate backup file ────────────────────────────────────────
if (-not (Test-Path $BackupPath)) {
    Write-Error "Backup file not found: $BackupPath"
    exit 1
}

$fileInfo = Get-Item $BackupPath
if ($fileInfo.Length -eq 0) {
    Write-Error "Backup file is empty: $BackupPath"
    exit 1
}

Write-Host "[WARNING] This will OVERWRITE the current production database."
Write-Host "         Backup file: $BackupPath ($([math]::Round($fileInfo.Length / 1MB, 2)) MB)"
Write-Host ""
Write-Host "Proceeding with restore in 5 seconds... (Ctrl+C to abort)"
Start-Sleep -Seconds 5

# ── Copy backup into container ──────────────────────────────────
$containerPath = "/tmp/restore.dump"
$composeCmd = "docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml"

Push-Location $ProjectRoot
try {
    Write-Host "[INFO] Copying backup into postgres container..."
    $copyCmd = "$composeCmd cp `"$BackupPath`" postgres:$containerPath"
    Invoke-Expression $copyCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to copy backup into container"
        exit 1
    }

    # ── Restore ─────────────────────────────────────────────────
    Write-Host "[INFO] Running pg_restore..."
    $restoreCmd = "$composeCmd exec -T postgres pg_restore -U scoutjobs -d scoutjobs --clean --if-exists $containerPath"
    Invoke-Expression $restoreCmd
    # pg_restore may return warnings (non-zero) but still succeed
    if ($LASTEXITCODE -gt 1) {
        Write-Error "pg_restore failed with exit code $LASTEXITCODE"
        exit 1
    }

    # ── Cleanup ─────────────────────────────────────────────────
    $cleanupCmd = "$composeCmd exec -T postgres rm -f $containerPath"
    Invoke-Expression $cleanupCmd | Out-Null

    Write-Host "[DONE] Database restore complete."
    Write-Host "       Verify with: docker compose exec postgres psql -U scoutjobs -d scoutjobs -c '\dt'"
}
finally {
    Pop-Location
}
