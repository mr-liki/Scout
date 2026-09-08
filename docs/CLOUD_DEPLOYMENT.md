# SCOUTJOBS Cloud Deployment

> **STATUS: OPTIONAL ALTERNATIVE -- NOT CURRENT PRODUCTION.**
> Current production is the local self-host architecture on the dedicated
> Windows PC with Docker Desktop -- see
> [`docs/LOCAL_PRODUCTION_DEPLOYMENT.md`](LOCAL_PRODUCTION_DEPLOYMENT.md).
> This document, `render.yaml`, `infra/render/`, and `test_render_cloud.py`
> are kept working as a documented fallback (e.g. if the Windows PC becomes
> unavailable) but nothing in local production depends on them.

This describes an optional cloud architecture: a fully managed stack with
no dependency on any local machine, Docker Desktop, WSL, or a Cloudflare
Tunnel.

```
                         INTERNET
                            |
                            v
            https://scout.apexora.workers.dev
                 Cloudflare Frontend
                            |
                            v
               Render FREE Web Service
             +--------------------------+
             |                          |
             | FastAPI                  |
             |     +                    |
             | ONE RQ LinkedIn Worker   |
             |                          |
             +-----------+----+---------+
                         |    |
                         v    v
                     Neon      Upstash
                  PostgreSQL    Redis
                     FREE        FREE
```

Render Free provides one process per web service, so `infra/render/start_render.py`
runs the existing FastAPI app and the existing single LinkedIn RQ worker as
two child processes inside that one container (see
[`infra/render/README.md`](../infra/render/README.md) for how it behaves).

This is a **separate deployment path** from local self-hosting:

| | Local / self-host | Cloud |
|---|---|---|
| Compute | `infra/docker-compose.prod.yml` (Windows/WSL) | Render Web Service |
| Database | Postgres container | Neon PostgreSQL |
| Cache/queue | Valkey container | Upstash Redis |
| Public exposure | Cloudflare Tunnel | Render's own HTTPS endpoint |

The Windows/self-host scripts under `infra/windows/` and `infra/selfhost/`
are untouched and remain available as an **optional self-host mode** -- they
are simply no longer the production path.

## Setup order

**Step 1 -- Create a Neon PostgreSQL database**
Create a free project at Neon. Note the database name.

**Step 2 -- Copy the Neon connection string**
Neon gives you a `postgresql://...?sslmode=require` URL. Keep the `sslmode`
(and `channel_binding`, if present) query parameters -- the app normalizes
only the URL scheme to `postgresql+psycopg://`, so all other parameters pass
through unchanged.

**Step 3 -- Create an Upstash Redis database**
Create a free database at Upstash, in TLS mode.

**Step 4 -- Copy the native Redis TLS connection URL**
This is the `rediss://default:PASSWORD@HOST:PORT` URL. Use it as-is; do not
downgrade it to `redis://`.

**Step 5 -- Create a Render Web Service from the GitHub repo**
Point it at `https://github.com/mr-liki/Scout`, Docker runtime, using
`render.yaml` (Blueprint) or by manually matching its settings:
Dockerfile `infra/Dockerfile.backend`, build context repo root, start
command `python infra/render/start_render.py`, health check path `/healthz`,
plan `free`.

**Step 6 -- Configure Render environment variables**
See the table below. `DATABASE_URL` and `REDIS_URL` are entered as secrets
in the Render dashboard (declared as `sync: false` in `render.yaml`, so
Render prompts for them rather than storing a value in the repo).

**Step 7 -- Deploy**
Render builds the Docker image and starts the container.

**Step 8 -- Migrations run automatically**
`start_render.py` runs `alembic upgrade head` (retrying transient Neon
connectivity failures) before starting the API or worker.

**Step 9 -- Verify `/healthz`**
`https://<your-service>.onrender.com/healthz` should return `200` immediately
-- it does not depend on the database, cache, or LinkedIn.

**Step 10 -- Verify `/readyz`**
Should report `database: ok` and `cache: ok` once Neon/Upstash are reachable.

**Step 11 -- Update `frontend/config.js`**
Change `apiBase: ""` to `apiBase: "https://<your-service>.onrender.com"`.
This step is intentionally **not** performed until the real Render URL
exists.

**Step 12 -- Commit the frontend config change**

**Step 13 -- Cloudflare auto-deploys the frontend**
`https://scout.apexora.workers.dev` picks up the new `apiBase`.

**Step 14 -- Perform one controlled, manual LinkedIn live test**
No automated live LinkedIn call is made as part of this deployment or its
tests.

## Render environment variables

| Variable | Value | Secret |
|---|---|---|
| `DATABASE_URL` | Neon connection string | YES |
| `REDIS_URL` | Upstash native TLS Redis URL | YES |
| `CORS_ORIGINS` | `https://scout.apexora.workers.dev` | NO |
| `SCOUT_ENV` | `production` | NO |
| `ENVIRONMENT` | `production` | NO |
| `LOG_LEVEL` | `INFO` | NO |
| `DEBUG` | `false` | NO |
| `APP_VERSION` | `2.0.0` | NO |
| `LINKEDIN_JOB_TIMEOUT_SECONDS` | `1200` | NO |
| `SEARCH_STALE_AFTER_SECONDS` | `1800` | NO |
| `SEARCH_CACHE_TTL_SECONDS` | `90` | NO |
| `DETAIL_CACHE_TTL_SECONDS` | `1800` | NO |
| `RATE_LIMIT_SEARCH_PER_MINUTE` | `10` | NO |
| `RATE_LIMIT_POLL_PER_MINUTE` | `60` | NO |
| `RATE_LIMIT_DETAIL_PER_MINUTE` | `20` | NO |
| `DB_POOL_SIZE` | `2` | NO |
| `DB_MAX_OVERFLOW` | `2` | NO |
| `DB_POOL_TIMEOUT` | `30` | NO |
| `DB_POOL_RECYCLE` | `300` | NO |

All non-secret values above are already declared in `render.yaml`.

## Render Free sleep behavior

Render Free suspends the service after inactivity. No keep-alive pinging is
implemented (none should be -- see below). On the next request:

1. Render cold-starts the container.
2. `start_render.py` runs migrations, then starts the API and worker.
3. Existing stale-search reconciliation (`reconcile_stale_searches`, run on
   worker startup) transitions any search that was interrupted mid-run to
   `partial` (if jobs were persisted) or `failed` (if not), with
   `stop_reason=worker_interrupted` and the exact resume offset preserved.
   `POST /api/v1/searches/{id}/resume` picks up from there.

No artificial keep-alive, self-pinging, external cron, or uptime-bot
workaround is used. Normal frontend polling of `GET /api/v1/searches/{id}`
while a user is waiting is legitimate traffic, not a workaround.

## Security notes

- `/healthz` and `/readyz` never return connection strings, hostnames, or
  credentials -- only `ok`/`unavailable` per dependency.
- Render terminates TLS; the API trusts Render's forwarded headers via
  Uvicorn's `--proxy-headers --forwarded-allow-ips=*` rather than trusting
  arbitrary client-supplied headers. `TRUST_CF_CONNECTING_IP` should stay
  `false` on Render (Render does not sit behind our Cloudflare Tunnel).
- CORS allows exactly `https://scout.apexora.workers.dev` in production --
  no wildcard.
