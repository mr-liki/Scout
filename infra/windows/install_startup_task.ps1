<#
.SYNOPSIS
    Install a Windows Scheduled Task that starts the SCOUTJOBS backend after logon.
.DESCRIPTION
    Registers a task that runs infra/windows/start_backend.ps1 a short delay after
    the specified user logs on. Docker Desktop is a per-user desktop application,
    so this task MUST run as the same interactive user account that runs Docker
    Desktop -- NOT as SYSTEM, which cannot see that user's Docker Desktop engine.
    Idempotent: re-running replaces any existing task of the same name rather
    than creating a duplicate.
.PARAMETER UserName
    The Windows account (DOMAIN\User or .\User) that runs Docker Desktop.
    Default: the account currently running this script.
.PARAMETER DelaySeconds
    Delay after logon before starting the backend. Default: 60.
.PARAMETER TaskName
    Scheduled task name. Default: "SCOUTJOBS Backend Startup".
#>
param(
    [string]$UserName = "$env:USERDOMAIN\$env:USERNAME",
    [int]$DelaySeconds = 60,
    [string]$TaskName = "SCOUTJOBS Backend Startup"
)

#Requires -RunAsAdministrator

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$scriptPath = Join-Path $repoRoot "infra\windows\start_backend.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Error "start_backend.ps1 not found at $scriptPath"
    exit 1
}

Write-Host "[INFO] Installing startup task '$TaskName' for user '$UserName'..."

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "[INFO] Removing existing task with the same name..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserName
$trigger.Delay = "PT${DelaySeconds}S"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2)

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
    -Description "Starts the SCOUTJOBS Docker backend after $UserName logs on (requires Docker Desktop running under the same account)." `
    -Force | Out-Null

Write-Host "[OK] Task '$TaskName' installed." -ForegroundColor Green
Write-Host "     Runs as: $UserName"
Write-Host "     Trigger: at logon, +${DelaySeconds}s delay"
Write-Host "     Script:  $scriptPath"
Write-Host ""
Write-Host "NOTE: This only starts the backend containers. Docker Desktop itself"
Write-Host "      must separately be configured to 'Start Docker Desktop when you"
Write-Host "      sign in' (Docker Desktop -> Settings -> General)."
