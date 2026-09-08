# SCOUTJOBS Task Scheduler Installer
# Installs Windows startup task for auto-recovery
# Run as Administrator

#Requires -RunAsAdministrator
#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$TaskName = "SCOUTJOBS WSL Startup"
$TaskDescription = "Starts SCOUTJOBS production stack in WSL2 on Windows startup"
$ScriptPath = "E:\Scout\infra\selfhost\start_scoutjobs.ps1"

Write-Host "========================================="
Write-Host "SCOUTJOBS Task Scheduler Installer"
Write-Host "========================================="
Write-Host ""

# Verify script exists
if (-not (Test-Path $ScriptPath)) {
    Write-Error "Startup script not found: $ScriptPath"
    exit 1
}

# Remove existing task if present
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create action
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""

# Create trigger (at startup)
$trigger = New-ScheduledTaskTrigger -AtStartup

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Create principal (run as SYSTEM with highest privileges)
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Register task
Write-Host "Creating scheduled task..."
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description $TaskDescription `
    -Force

Write-Host ""
Write-Host "========================================="
Write-Host "Task Scheduler Configuration Complete!"
Write-Host "========================================="
Write-Host ""
Write-Host "Task: $TaskName"
Write-Host "Trigger: At system startup"
Write-Host "Script: $ScriptPath"
Write-Host ""
Write-Host "To verify:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To manually run:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To remove:"
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName'"
