<#
.SYNOPSIS
    Stop the SCOUTJOBS production Docker stack.
.DESCRIPTION
    Gracefully stops all SCOUTJOBS containers without removing volumes.
    Does NOT affect other Docker projects.
.PARAMETER ProjectRoot
    Path to the project root. Default: E:\Scout
.PARAMETER RemoveContainers
    If specified, also removes stopped containers (keeps volumes).
#>
param(
    [string]$ProjectRoot,
    [switch]$RemoveContainers
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$composeFile = "$ProjectRoot\infra\docker-compose.prod.yml"
$envFile = "$ProjectRoot\infra\.env.production"

if (-not (Test-Path $composeFile)) {
    Write-Error "docker-compose.prod.yml not found at $ProjectRoot\infra"
    exit 1
}

Write-Host "[INFO] Stopping SCOUTJOBS services..."
# Both tunnel profiles are passed explicitly so `stop` reliably includes
# cloudflared (named tunnel) and/or cloudflared-quick (Quick Tunnel) whether
# or not they happen to be running -- never leaves either tunnel dangling.
$composeCmd = "docker compose --env-file `"$envFile`" -f `"$composeFile`" --profile tunnel --profile quick-tunnel"
Invoke-Expression "$composeCmd stop"

if ($RemoveContainers) {
    Write-Host "[INFO] Removing stopped containers (keeping volumes)..."
    Invoke-Expression "$composeCmd rm -f"
}

Write-Host "[DONE] SCOUTJOBS backend stopped." -ForegroundColor Green
Write-Host "       Data volumes (postgres_data, valkey_data) are preserved."
