<#
.SYNOPSIS
    Remove the SCOUTJOBS backend startup scheduled task.
.PARAMETER TaskName
    Scheduled task name. Default: "SCOUTJOBS Backend Startup".
#>
param(
    [string]$TaskName = "SCOUTJOBS Backend Startup"
)

#Requires -RunAsAdministrator

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $existingTask) {
    Write-Host "[INFO] Task '$TaskName' is not installed. Nothing to do."
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "[OK] Task '$TaskName' removed." -ForegroundColor Green
