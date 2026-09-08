# SCOUTJOBS Windows Startup Script
# Starts WSL2 and verifies production stack
# Used by Windows Task Scheduler for auto-start

#Requires -Version 5.1

$ErrorActionPreference = "Continue"
$LogFile = "E:\ScoutJobsBackups\Logs\scoutjobs-startup.log"

# Ensure log directory exists
New-Item -ItemType Directory -Force -Path "E:\ScoutJobsBackups\Logs" | Out-Null

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Write-Host $LogMessage
    Add-Content -Path $LogFile -Value $LogMessage
}

Write-Log "========================================="
Write-Log "SCOUTJOBS Startup Script"
Write-Log "========================================="

# Step 1: Start WSL if not running
Write-Log ""
Write-Log "Step 1: Starting WSL Ubuntu..."
$wslStatus = wsl -l -v 2>&1
if ($wslStatus -match "Running") {
    Write-Log "WSL is already running"
} else {
    Write-Log "Starting WSL Ubuntu..."
    wsl -d Ubuntu-24.04 -- echo "WSL started" | Out-Null
    Start-Sleep -Seconds 5
    Write-Log "WSL started"
}

# Step 2: Verify Docker is running
Write-Log ""
Write-Log "Step 2: Verifying Docker..."
$dockerCheck = wsl -d Ubuntu-24.04 -- docker info 2>&1
if ($dockerCheck -match "Server Version") {
    Write-Log "Docker is running"
} else {
    Write-Log "Starting Docker..."
    wsl -d Ubuntu-24.04 -- sudo systemctl start docker 2>&1 | Out-Null
    Start-Sleep -Seconds 10
    Write-Log "Docker started"
}

# Step 3: Start SCOUTJOBS services
Write-Log ""
Write-Log "Step 3: Starting SCOUTJOBS services..."
$startResult = wsl -d Ubuntu-24.04 -- sudo systemctl start scoutjobs 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Log "SCOUTJOBS services started"
} else {
    Write-Log "Warning: SCOUTJOBS start may have issues"
}

# Step 4: Verify services
Write-Log ""
Write-Log "Step 4: Verifying services..."
Start-Sleep -Seconds 15

# Check API health
$healthCheck = wsl -d Ubuntu-24.04 -- docker compose --env-file /opt/scoutjobs/infra/.env.production -f /opt/scoutjobs/infra/docker-compose.prod.yml exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Log "API is healthy"
} else {
    Write-Log "API health check pending (may still be starting)"
}

# Check services
$serviceStatus = wsl -d Ubuntu-24.04 -- docker compose --env-file /opt/scoutjobs/infra/.env.production -f /opt/scoutjobs/infra/docker-compose.prod.yml ps --format "{{.Name}}: {{.Status}}" 2>&1
Write-Log "Service status:"
$serviceStatus | ForEach-Object { Write-Log "  $_" }

Write-Log ""
Write-Log "========================================="
Write-Log "Startup Complete"
Write-Log "========================================="
