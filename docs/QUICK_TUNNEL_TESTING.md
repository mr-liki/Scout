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

## 1. Start the Quick Tunnel

Core services must already be running:

```powershell
.\infra\windows\start_backend.ps1
```

Then start the Quick Tunnel:

```powershell
.\infra\windows\start_backend.ps1 -IncludeQuickTunnel
```

This requires **no** `CLOUDFLARE_TUNNEL_TOKEN`. The script prints the
generated URL once cloudflared logs it. Equivalently, by hand:

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

## 4. Point the frontend at it (temporary, manual)

`frontend/config.js` is **not** updated automatically -- the URL changes
every time the tunnel restarts, so committing it would break as soon as the
tunnel is recreated. To test the real frontend against it:

1. Temporarily edit `frontend/config.js`:
   ```javascript
   // from:
   window.SCOUTJOBS_CONFIG = { apiBase: "" };
   // to:
   window.SCOUTJOBS_CONFIG = { apiBase: "https://xxxx.trycloudflare.com" };
   ```
2. Test locally (serve `frontend/` or open it directly).
3. **Revert this change before committing anything else.** Only commit it if
   you are deliberately doing a one-off deployed smoke test, and revert
   immediately after.

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
