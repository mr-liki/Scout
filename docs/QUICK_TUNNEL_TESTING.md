# Quick Tunnel Testing (Free, Temporary, Development Only)

> **This is for testing only. It is NOT production.** A production launch
> requires a real domain and the named tunnel described in
> [`docs/LOCAL_PRODUCTION_DEPLOYMENT.md`](LOCAL_PRODUCTION_DEPLOYMENT.md#manual-cloudflare-tunnel-setup-next-task).

Cloudflare's **Quick Tunnel** mode gives you a random, free
`https://xxxx.trycloudflare.com` URL that forwards to the backend, with:

- **No** Cloudflare account token
- **No** DNS zone or domain
- **No** permanent hostname

The URL is different every time the tunnel starts, and Cloudflare can drop it
at any time. Use it to test the real Cloudflare-Tunnel-to-Docker path (CORS,
`/healthz`, `/readyz`, a manual API call) before you own a domain -- never as
a long-lived backend URL.

```
Cloudflare
    |
    v
cloudflared-quick container (random trycloudflare.com hostname)
    |
    v
http://api:8000   (internal Docker network -- unchanged)
```

This uses a **separate** Docker Compose service (`cloudflared-quick`, profile
`quick-tunnel`) from the named tunnel (`cloudflared`, profile `tunnel`) --
starting or stopping one never touches the other, and the always-on named
production tunnel (if configured) is unaffected either way.

## 0. One-time setup: auto-sync to the Worker (recommended)

Because the URL changes on every restart, `start_backend.ps1 -IncludeQuickTunnel`
can automatically push the new URL to the deployed Cloudflare Worker's
`BACKEND_API_URL` binding, so `https://scout.apexora.workers.dev/api/*`
always works without ever visiting the Cloudflare dashboard. This uses the
Workers API directly (redeploying `frontend/worker.js` unchanged, with
`keep_assets: true` so static files aren't re-uploaded) -- see
`infra/windows/sync_worker_backend_url.py`. This sidesteps the dashboard
"Variables" propagation issue that caused the original 502s, since the
binding is written straight onto the live deployed version.

To enable it, add two values to `infra/.env.production` (gitignored, never
committed):

```
CLOUDFLARE_API_TOKEN=<see below>
CLOUDFLARE_ACCOUNT_ID=<see below>
```

**Create the API token:**
1. [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens) -> **Create Token**
2. Use **Create Custom Token**, add permission **Account > Workers Scripts > Edit**
3. Under **Account Resources**, select your account
4. Continue to summary -> **Create Token** -> copy it (shown once)

**Find the Account ID:** Cloudflare Dashboard -> Workers & Pages -> **scout**
-> Overview -> right-hand sidebar shows **Account ID**.

Both values are read only by `sync_worker_backend_url.py`, are never logged
or printed, and stay local (`infra/.env.production` is gitignored). Leave
either blank to skip auto-sync -- `start_backend.ps1` falls back to just
printing the URL for you to paste in manually.

## 1. Start the Quick Tunnel

Core services must already be running:

```powershell
.\infra\windows\start_backend.ps1
```

Then start the Quick Tunnel:

```powershell
.\infra\windows\start_backend.ps1 -IncludeQuickTunnel
```

This requires **no** `CLOUDFLARE_TUNNEL_TOKEN`. The script waits for the
generated URL to appear in logs, prints it, and -- if `CLOUDFLARE_API_TOKEN`
/ `CLOUDFLARE_ACCOUNT_ID` are configured (step 0 above) -- automatically
syncs it to the Worker's `BACKEND_API_URL`. Equivalently, by hand:

```powershell
docker compose --env-file infra\.env.production -f infra\docker-compose.prod.yml --profile quick-tunnel up -d cloudflared-quick
docker compose --env-file infra\.env.production -f infra\docker-compose.prod.yml --profile quick-tunnel logs cloudflared-quick
```

## 2. Copy the generated URL

Look for a line like:

```
Your quick Tunnel has been created! Visit it: https://random-word-word.trycloudflare.com
```

This URL is **not a secret** -- it's fine to see it in logs or share it while
testing. It just isn't stable.

## 3. Test it

```powershell
# Local (does not leave the machine)
curl http://localhost:8000/healthz   # only reachable from inside the api container -- see note below

# Through the Quick Tunnel (public)
curl https://xxxx.trycloudflare.com/healthz
curl https://xxxx.trycloudflare.com/readyz
```

`/healthz` should return `200` immediately. `/readyz` should return
`database: ok`, `cache: ok`. Note: `api:8000` is never published to the
Windows host, so "local" testing means running curl *inside* a container on
the `backend` network (e.g. `docker compose exec api curl http://localhost:8000/healthz`),
not from the Windows host's own `localhost`.

## 4. Point the frontend at it

`frontend/config.js` is **not**, and must never be, updated with a tunnel
URL -- it stays `apiBase: ""` (same-origin) permanently. That's the whole
point of the Worker proxy: `https://scout.apexora.workers.dev/api/*`
forwards to whatever `BACKEND_API_URL` currently is.

- **If auto-sync is enabled (step 0):** nothing to do -- once
  `start_backend.ps1 -IncludeQuickTunnel` finishes, the real deployed
  frontend already works against the current tunnel. To re-sync without a
  full restart (e.g. after the tunnel reconnected with a new URL on its
  own): `python infra\windows\sync_worker_backend_url.py https://<new-url>.trycloudflare.com`
- **If auto-sync is not enabled:** update `BACKEND_API_URL` manually in the
  Cloudflare Dashboard (Workers & Pages -> scout -> Settings -> Variables),
  under the **Production** environment specifically.
- To test `frontend/` served from somewhere else entirely (not the deployed
  Worker) against the Quick Tunnel directly, temporarily set
  `window.SCOUTJOBS_CONFIG.apiBase` in a local copy -- never commit that.

## 5. Allow the trycloudflare.com origin in CORS (only if testing the deployed frontend)

If you're testing the *deployed* frontend at `https://scout.apexora.workers.dev`
against the Quick Tunnel backend, CORS already allows that exact origin --
no change needed. If you're instead serving `frontend/` from some other local
origin (e.g. `http://localhost:8080`) and calling the Quick Tunnel API
directly, add it via `CORS_EXTRA_ORIGINS` in `infra/.env.production`:

```
CORS_EXTRA_ORIGINS=http://localhost:8080
```

Never set this (or `CORS_ORIGINS`) to `*`. Restart `api` to pick up the
change (`docker compose ... up -d --force-recreate api`), then revert it
back to blank when done testing.

## 6. Stop the Quick Tunnel

```powershell
.\infra\windows\stop_backend.ps1
```

This stops the Quick Tunnel container (and the named tunnel, if running)
without touching volumes or the core `postgres`/`valkey`/`api`/`linkedin_worker`
containers unless you stop those too. To stop only the Quick Tunnel:

```powershell
docker compose --env-file infra\.env.production -f infra\docker-compose.prod.yml --profile quick-tunnel stop cloudflared-quick
```

## Check current tunnel mode

```powershell
.\infra\windows\status.ps1
```

Reports one of: no tunnel, named tunnel running, or Quick Tunnel running
(clearly labeled as testing-only).

## For real production

Quick Tunnel URLs are randomly generated and can disappear at any time --
they are never suitable for `frontend/config.js` on `main`. For a stable
production backend URL, follow the **named tunnel** setup in
[`docs/LOCAL_PRODUCTION_DEPLOYMENT.md`](LOCAL_PRODUCTION_DEPLOYMENT.md#manual-cloudflare-tunnel-setup-next-task),
which requires a Cloudflare-managed domain/zone you control.
