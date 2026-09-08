<#
.SYNOPSIS
    Report whether this Windows PC is ready to run SCOUTJOBS as a always-on host.
.DESCRIPTION
    Read-only diagnostic. Reports Docker status, AC sleep configuration, network
    status, backup directory availability, and disk free space. Never changes
    any Windows power setting -- if sleep is enabled, this script only tells
    the user what to change manually.
.PARAMETER BackupDir
    Backup directory to check. Default: E:\ScoutJobsBackups\PostgreSQL
#>
param(
    [string]$BackupDir = "E:\ScoutJobsBackups\PostgreSQL"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SCOUTJOBS Host Readiness Check" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Docker status ───────────────────────────────────────────────
Write-Host "Docker:" -ForegroundColor Yellow
docker info 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Docker engine is running" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Docker engine is not reachable" -ForegroundColor Red
}

# ── AC sleep configuration (report only, never changed) ─────────
Write-Host ""
Write-Host "Power (AC sleep setting):" -ForegroundColor Yellow
try {
    $powerOutput = powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null
    $acLine = $powerOutput | Select-String "Current AC Power Setting Index:"
    if ($acLine) {
        $hexValue = ($acLine -split ":")[-1].Trim()
        $seconds = [Convert]::ToInt64($hexValue, 16)
        if ($seconds -eq 0) {
            Write-Host "  [OK] Sleep while plugged in: Never" -ForegroundColor Green
        } else {
            $minutes = [math]::Round($seconds / 60, 1)
            Write-Host "  [WARN] Sleep while plugged in: $minutes minute(s)" -ForegroundColor Yellow
            Write-Host "         Recommended: Settings -> System -> Power -> Sleep -> 'Never' (while plugged in)"
        }
    } else {
        Write-Host "  [WARN] Could not determine AC sleep setting" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [WARN] Could not query power settings: $($_.Exception.Message)" -ForegroundColor Yellow
}
Write-Host "  (This script never changes power settings -- change manually if needed.)"

# ── Network status ──────────────────────────────────────────────
Write-Host ""
Write-Host "Network:" -ForegroundColor Yellow
try {
    $ping = Test-Connection -ComputerName "1.1.1.1" -Count 1 -Quiet -ErrorAction Stop
    if ($ping) {
        Write-Host "  [OK] Internet reachable" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Internet not reachable" -ForegroundColor Red
    }
} catch {
    Write-Host "  [WARN] Could not test connectivity: $($_.Exception.Message)" -ForegroundColor Yellow
}

# ── Backup directory ────────────────────────────────────────────
Write-Host ""
Write-Host "Backup Directory:" -ForegroundColor Yellow
if (Test-Path $BackupDir) {
    Write-Host "  [OK] $BackupDir exists" -ForegroundColor Green
    try {
        $probe = Join-Path $BackupDir ".write_test_$([guid]::NewGuid()).tmp"
        [IO.File]::WriteAllText($probe, "ok")
        Remove-Item $probe -Force
        Write-Host "  [OK] Directory is writable" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] Directory is not writable: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "  [WARN] $BackupDir does not exist yet (created on first backup)" -ForegroundColor Yellow
}

# ── Disk free space ─────────────────────────────────────────────
Write-Host ""
Write-Host "Disk Free Space:" -ForegroundColor Yellow
try {
    $driveLetter = (Split-Path -Qualifier $BackupDir).TrimEnd(":")
    $drive = Get-PSDrive -Name $driveLetter -ErrorAction Stop
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    Write-Host "  ${driveLetter}: drive free space: $freeGB GB"
    if ($freeGB -lt 5) {
        Write-Host "  [WARN] Less than 5 GB free" -ForegroundColor Yellow
    } else {
        Write-Host "  [OK]" -ForegroundColor Green
    }
} catch {
    Write-Host "  [WARN] Could not determine free disk space: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
