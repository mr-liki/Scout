# SCOUTJOBS Production Deployment Guide

> **NOTE:** This document describes an older WSL2/systemd-based self-host
> approach. Current production runs the same Docker Compose stack directly
> under **Docker Desktop on Windows** (no WSL2 Ubuntu distro, no systemd) --
> see [`docs/LOCAL_PRODUCTION_DEPLOYMENT.md`](LOCAL_PRODUCTION_DEPLOYMENT.md)
> for the current, verified procedure (`infra/windows/*.ps1`).

## Self-Hosted WSL2 Architecture

```
                            USERS
                              |
                +-------------+-------------+
                |                           |
                v                           v
        Cloudflare Pages             Cloudflare DNS
        SCOUTJOBS frontend                    |
                |                             |
                | HTTPS API                   v
                +-------------------- Cloudflare Tunnel
                                              |
                                              |
                                     outbound tunnel only
                                              |
                                              v
                              Dedicated Windows Production PC
                                              |
                                              v
                                        WSL2 Ubuntu 24.04
                                              |
                                              v
                                       Docker Engine
                                              |
                          +-------------------+-------------------+
                          |                   |                   |
                          v                   v                   v
                       FastAPI            PostgreSQL            Valkey
                       2 workers             16               cache/queue
                          |
                          |
                          v
                       RQ queue
                          |
                          v
                  LinkedIn worker = 1
                          |
                          v
                  linkedin_connector.py
                          |
                          v
              Public LinkedIn guest endpoints
```

## 1. Hardware Requirements

### Minimum
- 4 CPU threads
- 8 GB RAM
- 50 GB free SSD
- Wired network connection

### Recommended
- 6+ CPU threads
- 16 GB RAM
- 150+ GB free SSD
- Wired Ethernet
- UPS (for power failure recovery)

## 2. Windows Prerequisites

### Enable Virtualization
1. Open Task Manager → Performance tab
2. Verify "Virtualization: Enabled"
3. If disabled, enable in BIOS/UEFI

### Required Windows Features
```powershell
# Run in PowerShell as Administrator
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

### Restart Windows after enabling features

## 3. WSL2 Installation

### Install WSL2
```powershell
# Run in PowerShell as Administrator
wsl --install -d Ubuntu-24.04
```

### Restart Windows

### Complete Ubuntu Setup
1. Ubuntu terminal will open automatically
2. Create username and password
3. Wait for installation to complete

### Verify WSL2
```powershell
wsl --status
wsl -l -v
```

Expected output:
```
  NAME              STATE           VERSION
* Ubuntu-24.04      Running         2
```

## 4. Ubuntu systemd Support

### Enable systemd
```bash
# Inside WSL Ubuntu
sudo tee /etc/wsl.conf > /dev/null << 'EOF'
[boot]
systemd=true
EOF
```

### Restart WSL
```powershell
# From Windows PowerShell
wsl --shutdown
```

### Restart Ubuntu and verify
```bash
# Inside WSL Ubuntu
systemctl --version
```

## 5. Docker Engine Installation

### Install Docker (inside WSL Ubuntu)
```bash
# Update packages
sudo apt update
sudo apt upgrade -y

# Install required packages
sudo apt install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
```

### Log out and back in for group changes

### Verify Docker
```bash
docker version
docker compose version
docker run --rm hello-world
```

## 6. WSL2 Storage Strategy

### Production Data Layout
```
WSL2 Ubuntu filesystem (ext4):
  /opt/scoutjobs          - Production repository
  /var/lib/docker         - Docker data root
  /var/log/scoutjobs      - Application logs

Windows filesystem (NTFS):
  E:\ScoutJobsBackups\PostgreSQL - Database backups
  E:\ScoutJobsBackups\Logs       - Log archives
```

### Important
- PostgreSQL and Valkey data MUST remain on WSL2 ext4 filesystem
- Do NOT use /mnt/c, /mnt/d, /mnt/e for database volumes
- Windows NTFS may be used for backups only

## 7. Production Repository

### Clone Repository
```bash
# Inside WSL Ubuntu
sudo mkdir -p /opt
sudo chown $USER:$USER /opt
cd /opt
git clone <YOUR_REPO_URL> scoutjobs
cd scoutjobs
```

### Windows Development
- Development repository: `E:\Scout`
- Production repository: `/opt/scoutjobs`
- Deployment: Git push → production pull

## 8. Production Environment

### Configure Environment
```bash
cd /opt/scoutjobs
cp infra/.env.production.example infra/.env.production
nano infra/.env.production
```

### Required Configuration
- `POSTGRES_PASSWORD`: Generate strong password
- `CLOUDFLARE_TUNNEL_TOKEN`: From Cloudflare setup
- `CORS_ORIGINS`: Your frontend URL

Generate strong password:
```bash
openssl rand -base64 32
```

## 9. Docker Compose

### Architecture
- **postgres**: PostgreSQL 16 (Alpine)
- **valkey**: Valkey 8 (Alpine)
- **api**: FastAPI with 2 Uvicorn workers
- **linkedin_worker**: RQ worker (exactly 1)
- **cloudflared**: Cloudflare Tunnel

### No Public Ports
- PostgreSQL 5432: Internal only
- Valkey 6379: Internal only
- FastAPI 8000: Internal only
- Public access via Cloudflare Tunnel only

## 10. First Deployment

```bash
cd /opt/scoutjobs

# Make scripts executable
chmod +x infra/scripts/*.sh
chmod +x infra/selfhost/*.sh

# Run deployment
./infra/scripts/deploy.sh
```

## 11. Cloudflare Setup

### Create Cloudflare Account
1. Sign up at cloudflare.com (free)
2. Add your domain or use .pages.dev

### Create Tunnel
1. Go to Zero Trust → Networks → Tunnels
2. Create tunnel named `scoutjobs-prod`
3. Copy tunnel token
4. Add to `infra/.env.production`:
   ```
   CLOUDFLARE_TUNNEL_TOKEN=your_token_here
   ```

### Configure Tunnel
1. Add public hostname:
   - Hostname: `api.YOUR_DOMAIN`
   - Service: `http://api:8000`

### Cloudflare Pages
1. Go to Pages → Create project
2. Connect to GitHub repository
3. Configure:
   - Build command: (empty)
   - Build output: `frontend`

## 12. Auto-Start Configuration

### Install Systemd Services
```bash
cd /opt/scoutjobs
sudo ./infra/selfhost/install_systemd_services.sh
```

### Install Windows Startup Task
```powershell
# Run as Administrator
E:\Scout\infra\selfhost\install_startup_task.ps1
```

### Verify Auto-Start
```bash
# Inside WSL
sudo systemctl status scoutjobs
systemctl list-timers | grep scoutjobs
```

## 13. Backup Configuration

### Manual Backup
```bash
cd /opt/scoutjobs
sudo ./infra/scripts/backup_postgres.sh
```

### Automated Backup
- Runs daily at 02:00 via systemd timer
- Backups stored at: `E:\ScoutJobsBackups\PostgreSQL`
- Retention: 14 days

### Verify Backup
```bash
ls -la /mnt/e/ScoutJobsBackups/PostgreSQL
```

## 14. Monitoring Commands

### Service Status
```bash
# Docker services
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml ps

# Systemd
sudo systemctl status scoutjobs
systemctl list-timers | grep scoutjobs
```

### Logs
```bash
# Recent logs
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml logs --tail=100

# Follow logs
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml logs -f
```

### Resource Usage
```bash
docker stats --no-stream
df -h
free -h
```

## 15. Troubleshooting

### API Not Responding
```bash
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml logs api | tail -50
```

### Worker Not Processing
```bash
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml logs linkedin_worker | tail -50
```

### Database Issues
```bash
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml exec postgres pg_isready -U scoutjobs
```

### WSL Not Starting
```powershell
# From Windows
wsl --shutdown
wsl -d Ubuntu-24.04
```

### Docker Not Starting
```bash
sudo systemctl start docker
sudo systemctl status docker
```

## 16. Rollback Procedure

### Application Rollback
```bash
cd /opt/scoutjobs

# Backup current state
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml exec postgres \
  pg_dump -Fc -U scoutjobs -d scoutjobs > /tmp/pre-rollback.dump

# Checkout previous version
git log --oneline -10
git checkout <PREVIOUS_COMMIT_SHA>

# Rebuild and restart
./infra/scripts/deploy.sh
```

### Database Restore
```bash
./infra/scripts/restore_postgres.sh /tmp/pre-rollback.dump
```

## 17. Security Checklist

- [ ] Windows: Dedicated admin user
- [ ] Windows: Strong login password
- [ ] Windows: Automatic security updates
- [ ] Windows: BitLocker enabled (if available)
- [ ] Windows: No public RDP exposure
- [ ] Windows: Windows Defender enabled
- [ ] WSL: Docker running as non-root
- [ ] WSL: No public SSH server
- [ ] Application: No secrets in Git
- [ ] Application: .env.production not committed
- [ ] Network: No public database ports
- [ ] Network: No public cache ports
- [ ] Network: API via Cloudflare Tunnel only
- [ ] Network: No router port forwarding

## 18. Power Failure Recovery

### BIOS Configuration
- Enable "Restore on AC Power Loss = Power On" (if available)

### Recovery Flow
```
Power returns
    ↓
Windows boots
    ↓
Task Scheduler starts WSL
    ↓
Docker starts
    ↓
systemd starts scoutjobs.service
    ↓
Compose containers start
    ↓
Worker reconciliation fixes stale searches
    ↓
Cloudflare Tunnel reconnects
```

### Verify Recovery
```bash
# After power failure recovery
sudo systemctl status scoutjobs
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml ps
curl https://api.YOUR_DOMAIN/healthz
```

## 19. WSL Maintenance

### VHDX Growth
WSL2 virtual disk grows as needed but may not auto-shrink.

### Safe Compaction
```powershell
# From Windows (WSL must be shut down)
wsl --shutdown
# Compact using diskpart or Optimize-VHD if Hyper-V available
```

### Disk Space Monitoring
```bash
df -h /
```

## 20. Network Requirements

### Required
- Outbound HTTPS (443) for Cloudflare Tunnel
- Outbound HTTP (80) for package updates

### NOT Required
- No inbound ports
- No router port forwarding
- No DMZ configuration
- No static IP required
- No dynamic DNS for API

## 21. Smoke Test

### First Live Search
```bash
curl -X POST https://api.YOUR_DOMAIN/api/v1/searches \
  -H "Content-Type: application/json" \
  -d '{
    "keywords": "Software Engineer",
    "location": "India",
    "posted_within": "1h",
    "under_10": false,
    "max_jobs": 10,
    "max_pages": 3
  }'

# Poll status
curl https://api.YOUR_DOMAIN/api/v1/searches/<SEARCH_ID>
```

## 22. Multi-User Test

Simulate 10 identical searches:
```bash
for i in {1..10}; do
  curl -X POST https://api.YOUR_DOMAIN/api/v1/searches \
    -H "Content-Type: application/json" \
    -d '{"keywords":"Python Developer","location":"India"}' &
done
wait
```

Expected:
- One normalized query hash
- One LinkedIn upstream scan
- Duplicate callers reuse active search

## 23. Reboot Test

```bash
# Before reboot
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml ps

# Reboot Windows
# After reboot, verify automatically
sudo systemctl status scoutjobs
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml ps
curl https://api.YOUR_DOMAIN/healthz
```

## 24. Monthly Cost

**₹0 / $0**

- Cloudflare Pages: Free
- Cloudflare Tunnel: Free
- Cloudflare DNS: Free
- Docker: Free
- PostgreSQL: Free
- Valkey: Free
- LinkedIn public API: Free
- Hardware: One-time purchase
- Electricity: ~₹200-500/month (varies)
