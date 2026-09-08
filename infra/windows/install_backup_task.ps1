<#
.SYNOPSIS
    Install a daily Windows Scheduled Task that backs up the SCOUTJOBS database.
.DESCRIPTION
    Registers a task that runs infra/windows/backup_postgres.ps1 once daily.
    Must run as the same interactive user account that runs Docker Desktop --
    NOT SYSTEM, which cannot reach that user's Docker engine. No database
    password is passed as a task argument; backup_postgres.ps1 authenticates
    via the running postgres container, not a command-line credential.
    Idempotent: re-running replaces any existing task of the same name.
.PARAMETER UserName
    The Windows account (DOMAIN\User or .\User) that runs Docker Desktop.
    Default: the account currently running this script.
.PARAMETER Time
    Local time to run the daily backup, e.g. "02:00". Default: "02:00".
.PARAMETER TaskName
    Scheduled task name. Default: "SCOUTJOBS Daily Backup".
#>
param(
    [string]$UserName = "$env:USERDOMAIN\$env:USERNAME",
    [string]$Time = "02:00",
    [string]$TaskName = "SCOUTJOBS Daily Backup"
)

#Requires -RunAsAdministrator

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$scriptPath = Join-Path $repoRoot "infra\windows\backup_postgres.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Error "backup_postgres.ps1 not found at $scriptPath"
    exit 1
}

$startTime = [DateTime]::Parse($Time)

Write-Host "[INFO] Installing daily backup task '$TaskName' for user '$UserName' at $Time..."

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "[INFO] Removing existing task with the same name..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At $startTime

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal `
    -UserId $UserName `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Runs a daily SCOUTJOBS PostgreSQL backup ($($scriptPath))." `
    -Force | Out-Null

Write-Host "[OK] Task '$TaskName' installed." -ForegroundColor Green
Write-Host "     Runs as: $UserName"
Write-Host "     Trigger: daily at $Time"
Write-Host "     Script:  $scriptPath"
Write-Host ""
Write-Host "NOTE: The task only runs when $UserName is logged on and Docker Desktop"
Write-Host "      is running (StartWhenAvailable will catch up a missed run)."
