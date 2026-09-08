# SCOUTJOBS Local Production Deployment (Current Architecture)

This is the **current production architecture**: the backend runs on a
dedicated Windows PC via Docker Desktop; the frontend is hosted globally on
Cloudflare. Render/Neon/Upstash (`render.yaml`, `infra/render/`,
`docs/CLOUD_DEPLOYMENT.md`) are kept working as an **optional alternative**,
not the current path.

```
                   INTERNET
                      |
                      v
        Cloudflare Workers Static Assets
        https://scout.apexora.workers.dev
                      |
                      | HTTPS API requests
                      v
               Cloudflare Edge
                      |
                      v
            Named Cloudflare Tunnel
                      |
                      v
             Windows Production PC
                 Docker Desktop
        +-------------------------------+
        |                               |
        | cloudflared                   |
        |      |                        |
        |      v                        |
        | FastAPI :8000                 |
        |      |                        |
        |      +-- PostgreSQL 16        |
        |      +-- Valkey 8             |
        |      +-- ONE RQ worker        |
        |                  |            |
        +------------------+------------+
                           |
                           v
                 LinkedIn public guest
                    job endpoints
```

Cloudflare Tunnel carries **inbound** API traffic only. The LinkedIn worker's
requests to LinkedIn's public guest endpoints go **outbound** over the PC's
normal internet connection -- they are never proxied through Cloudflare.

## Compose project

The Docker Compose project name is implicit: **`infra`** (derived from the
`infra/` directory containing `docker-compose.prod.yml`). This produces
container/volume names like `infra-postgres-1` and `infra_postgres_data`.
**Never pass `-p <name>`** or rename the project -- doing so creates a
second, empty set of volumes and makes the production database appear to
have vanished.

## Services

| Service | Image | Purpose | Published ports |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | Database (`scoutjobs`) | none (internal `5432/tcp` only) |
| `valkey` | `valkey/valkey:8-alpine` | Cache/queue/rate-limit store | none (internal `6379/tcp` only) |
| `api` | built from `infra/Dockerfile.backend` | FastAPI | none (internal `8000/tcp` only) |
| `linkedin_worker` | built from `infra/Dockerfile.backend` | exactly ONE RQ worker | none |
| `cloudflared` (opt-in, `profiles: [tunnel]`) | `cloudflare/cloudflared` | inbound tunnel only | none |

No service publishes a host port. `postgres`, `valkey`, and `api` are only
reachable from other containers on the internal `backend` Docker network.
Because nothing is exposed to `0.0.0.0`, no Windows Firewall inbound rule is
needed or should be created for 5432, 6379, or 8000.

## Day-to-day operations

All scripts live in `infra/windows/` and resolve their own repo root, so
they can be run from any working directory (`.\infra\windows\<script>.ps1`
or a full path).

```powershell
# Start (idempotent -- safe to re-run)
.\infra\windows\start_backend.ps1

# Start including the Cloudflare Tunnel (once a token is configured)
.\infra\windows\start_backend.ps1 -IncludeTunnel

# Status (containers, health, tunnel, volumes, latest backup, disk usage)
.\infra\windows\status.ps1

# Stop (never removes volumes)
.\infra\windows\stop_backend.ps1

# One-off backup
.\infra\windows\backup_postgres.ps1

# Restore (requires -Confirm RESTORE)
.\infra\windows\restore_postgres.ps1 -BackupPath <path> -Confirm RESTORE

# Read-only host readiness report (Docker, power, network, disk, backups)
.\infra\windows\check_host_readiness.ps1
```

`start_backend.ps1` waits for the Docker engine (retrying every 5s for up
to ~2 minutes), starts `postgres`/`valkey` and waits for health, applies
pending Alembic migrations (`alembic upgrade head`), then starts `api` and
`linkedin_worker` and waits for health. With `-IncludeTunnel`, it checks
`CLOUDFLARE_TUNNEL_TOKEN` first -- if blank, it prints "Cloudflare Tunnel
token is not configured. Core SCOUTJOBS backend remains running." and skips
`cloudflared` rather than starting it with an empty token.

## Auto-start on the production PC

Docker Desktop is a per-user desktop application, not a Windows service --
if the production account is not signed in, Docker Desktop is not running,
so **the production PC must stay signed in** as the account that runs
Docker Desktop. There is no way around this on Docker Desktop for Windows;
this is not equivalent to a server-grade Linux init system.

1. Docker Desktop -> Settings -> General -> enable **"Start Docker Desktop
   when you sign in"** (manual step; this is never changed programmatically).
2. Install the backend startup task (run as Administrator, once):
   ```powershell
   .\infra\windows\install_startup_task.ps1
   ```
   This registers a Scheduled Task that runs `start_backend.ps1` ~60s after
   the same account logs on (the account running Docker Desktop -- **not**
   SYSTEM, which cannot see that user's Docker engine). Remove with
   `.\infra\windows\uninstall_startup_task.ps1`.
3. Configure Windows power settings manually: **Settings -> System -> Power
   -> Sleep -> "Screen and sleep" -> Sleep: Never** while plugged in. The
   display may turn off; the PC must not sleep. `check_host_readiness.ps1`
   reports the current setting but never changes it.

## Daily backups

```powershell
# Install (run as Administrator, once)
.\infra\windows\install_backup_task.ps1

# Remove
.\infra\windows\uninstall_backup_task.ps1
```

Runs `backup_postgres.ps1` daily at 02:00 local time (override with
`-Time "HH:mm"`) as the same interactive account that runs Docker Desktop.
Backups are `pg_dump -Fc` files at
`E:\ScoutJobsBackups\PostgreSQL\scoutjobs-<UTC timestamp>.dump`, validated
(non-empty, `pg_restore --list` succeeds), retained for 14 days, and never
overwritten. No database password is ever passed as a task argument --
`backup_postgres.ps1` authenticates through the already-running `postgres`
container.

## Restore

```powershell
.\infra\windows\restore_postgres.ps1 -BackupPath "E:\ScoutJobsBackups\PostgreSQL\scoutjobs-....dump" -Confirm RESTORE
```

`-Confirm RESTORE` is mandatory (an empty or wrong value is rejected by
PowerShell parameter validation before anything runs). The script verifies
the file exists, is non-empty, and that `pg_restore --list` succeeds before
touching the database.

## Manual Cloudflare Tunnel setup (next task)

The backend already runs fully without a tunnel. When ready to expose it:

1. Open the [Cloudflare Dashboard](https://dash.cloudflare.com) -> **Zero
   Trust** -> **Networks** -> **Tunnels**.
2. **Create a tunnel**, connector type **cloudflared**.
3. Name it **`scout-backend`**.
4. Copy the **Docker** token shown (a long string) -- do **not** paste it
   into any source file.
5. Put it into `infra/.env.production` as:
   ```
   CLOUDFLARE_TUNNEL_TOKEN=<paste the token here>
   ```
   This file is already gitignored and is never committed.
6. Add a **public hostname** for the tunnel. Service type **HTTP**, URL
   **`http://api:8000`** (the Docker service name/port -- reachable only
   from inside the `infra` Compose network).
7. Start the backend with the tunnel:
   ```powershell
   .\infra\windows\start_backend.ps1 -IncludeTunnel
   ```
8. Verify: `docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml --profile tunnel logs cloudflared` shows a healthy connection.
9. Verify `https://<your tunnel hostname>/healthz` returns `200`.
10. Verify `https://<your tunnel hostname>/readyz` returns `database: ok`, `cache: ok`.
11. Update `frontend/config.js` `apiBase` to the real hostname, commit, and
    push to `main` -- Cloudflare auto-deploys the frontend from there. This
    step is intentionally **not** done as part of backend implementation,
    since the real hostname does not exist yet.

### Domain requirement

A **permanent** named-tunnel public hostname requires a Cloudflare-managed
DNS zone/domain that you control (e.g. `api.example.com`) -- **not**
`apexora.workers.dev`, which is the Cloudflare Workers account subdomain
used for the frontend and is not available for Tunnel public-hostname DNS
routing. If no such domain exists yet:

- `cloudflared tunnel --url http://api:8000` ("Quick Tunnel") can be used
  for **temporary testing only** -- it prints a random `trycloudflare.com`
  hostname that can change on every restart.
- Do **not** put a Quick Tunnel URL into `frontend/config.js`. It is not
  suitable for permanent production configuration.

## FREE Quick Tunnel Test Mode

For testing the real Cloudflare-Tunnel-to-Docker path before a domain
exists, a second opt-in Compose profile provides a free, temporary tunnel:

```powershell
.\infra\windows\start_backend.ps1 -IncludeQuickTunnel
```

- **No domain required.**
- **No token required** (`CLOUDFLARE_TUNNEL_TOKEN` stays blank; there is no
  separate "quick tunnel token" -- none exists for this mode).
- Generates a **temporary** `https://xxxx.trycloudflare.com` URL, different
  every time, printed directly in the container logs (not a secret).
- Runs as its own Compose service (`cloudflared-quick`, profile
  `quick-tunnel`), completely separate from the named `cloudflared` service
  (profile `tunnel`) -- starting or stopping one never touches the other.
- **Not suitable for production.** The URL is not stable and is not written
  to `frontend/config.js` automatically.

Full walkthrough (starting, reading the URL, temporarily testing the
frontend against it, `CORS_EXTRA_ORIGINS`, stopping it) is in
[`docs/QUICK_TUNNEL_TESTING.md`](QUICK_TUNNEL_TESTING.md).

## CORS and client IP

- Production CORS allows exactly `https://scout.apexora.workers.dev` (no
  wildcard). Configured via `CORS_ORIGINS` in `infra/.env.production`.
- `CORS_EXTRA_ORIGINS` (optional, comma-separated) allows temporarily adding
  origins on top of `CORS_ORIGINS` -- e.g. a Quick Tunnel URL while testing.
  Never set to `*`; leave blank in normal operation.
- `TRUST_CF_CONNECTING_IP=true` in production: the API trusts the
  `CF-Connecting-IP` header (set by `cloudflared`/Cloudflare edge) for rate
  limiting, and falls back to the raw socket address otherwise. No other
  header (`X-Real-IP`, `X-Client-IP`, etc.) is trusted. This is safe because
  no port is published to the host -- the tunnel is the only path in, so a
  client cannot reach the API directly to spoof the header.

## Stale search recovery

Unchanged: `SEARCH_STALE_AFTER_SECONDS=1800`. If the worker is interrupted
(machine sleep, network loss, container restart) mid-search, on next worker
startup `reconcile_stale_searches()` transitions any search still marked
`running` past that threshold to `partial` (jobs were persisted) or `failed`
(none were), with `stop_reason=worker_interrupted`, preserving the exact
LinkedIn resume offset. `POST /api/v1/searches/{id}/resume` continues from
there. Docker's `restart: unless-stopped` policy and cloudflared's own
reconnect logic handle transient failures without any custom watchdog.

## Troubleshooting

| Symptom | Check |
|---|---|
| Containers won't start | `.\infra\windows\check_host_readiness.ps1`, then `docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml logs` |
| `/healthz` fails | `docker compose ... logs api` |
| `/readyz` shows `unavailable` | `docker compose ... exec postgres pg_isready -U scoutjobs`, `docker compose ... exec valkey valkey-cli ping` |
| No LinkedIn jobs found | Check `linkedin_worker` logs -- connector issues are independent of this deployment's networking |
| Tunnel not connecting | `docker compose ... --profile tunnel logs cloudflared` (never share this log externally; it does not print the token, but confirm before pasting into an issue) |
| Database "empty" after a change | Confirm the Compose project name is still `infra` (`docker compose ... ps` should show `infra-postgres-1`, not a different prefix) and that `infra_postgres_data` volume still exists (`docker volume ls`) |

## Cost

Cloudflare Workers Static Assets, Cloudflare Tunnel, PostgreSQL, Valkey, and
LinkedIn's public guest endpoints are all free. The only ongoing cost is the
production PC's electricity.
