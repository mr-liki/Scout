# Cloudflare Worker API Proxy

The browser talks to exactly one URL: `https://scout.apexora.workers.dev`.
That single Worker serves the static frontend **and** proxies `/api/*`
server-side to the backend (reached through a Cloudflare Tunnel on the
Docker Desktop production PC). The tunnel hostname is never sent to, or
visible from, the browser.

```
Browser
   |
   v
https://scout.apexora.workers.dev
   |
   v
Cloudflare Worker (frontend/worker.js)
   |
   +-- path starts with /api/  --> proxy to env.BACKEND_API_URL
   |
   +-- everything else         --> env.ASSETS.fetch(request)  (static files)
                                          |
                                          v
                              Cloudflare Tunnel (named or Quick Tunnel)
                                          |
                                          v
                                 Docker Desktop: FastAPI :8000
```

## What changed for the frontend

- `frontend/js/api.js` now calls `/api/healthz` (was `/healthz`) so every
  backend call goes through the `/api/*` prefix the Worker proxies.
  `/api/v1/searches`, `/api/v1/searches/{id}`, `/api/v1/searches/{id}/resume`,
  and `/api/jobs/linkedin/{id}` were already called with an `/api/` prefix
  and needed no change.
- `frontend/config.js` `apiBase` stays `""` (same-origin). It must **not**
  contain a `trycloudflare.com` URL, ever -- the Worker is what knows the
  backend's address, not the browser.

## Why `/api/healthz` and `/api/readyz` are special-cased

FastAPI's actual routes are `/healthz` and `/readyz` (no `/api` prefix) --
this task does not modify FastAPI routes. So the Worker aliases just those
two paths (`/api/healthz` -> backend `/healthz`, `/api/readyz` -> backend
`/readyz`) and forwards every other `/api/*` path unchanged, since those
already match real backend routes (`/api/v1/...`, `/api/jobs/linkedin/...`).

## `frontend/worker.js`

The Worker's `fetch(request, env)` handler:

1. Parses the request URL.
2. If the pathname starts with `/api/`, forwards the request to
   `env.BACKEND_API_URL` (method, whitelisted headers, query string, and
   body preserved) and returns the backend's response **unchanged**.
3. Otherwise, serves the static frontend via `env.ASSETS.fetch(request)`.

Only `Content-Type`, `Accept`, and `Authorization` (if ever added) are
forwarded to the backend -- cookies and Cloudflare-internal headers are not
relayed. If `BACKEND_API_URL` is unset, or the backend fetch fails for any
reason (tunnel down, DNS failure, etc.), the Worker returns:

```
HTTP 502
{"error": "Backend unavailable"}
```

The tunnel hostname, any stack trace, and any other internal detail are
never included in that response (the underlying error is only logged
server-side via `console.error`, visible in `wrangler tail`/dashboard logs,
not to the client).

## `wrangler.toml`

Adding custom Worker code (the proxy) alongside static assets requires a
`wrangler.toml` -- previously this project had none, since a pure
dashboard-managed "Workers Static Assets" site needs no repo config. It
declares:

- `main = "frontend/worker.js"` -- the Worker entry point
- `[assets] directory = "./frontend"`, `binding = "ASSETS"` -- static files,
  reachable in the Worker as `env.ASSETS`
- `compatibility_date` -- required by Workers

**If deployment breaks after this change**, check the Cloudflare dashboard
build settings (Workers & Pages -> `scout` -> Settings -> Build): if the
configured "Root directory" is not the repository root, move `wrangler.toml`
(keeping `main`/`[assets].directory` paths relative to its new location) to
match. This could not be verified from the repository alone.

## Configuring `BACKEND_API_URL` (Cloudflare Dashboard)

1. Open the [Cloudflare Dashboard](https://dash.cloudflare.com).
2. **Workers & Pages** -> **scout**.
3. **Settings** -> **Variables**.
4. Add a variable:
   - Name: `BACKEND_API_URL`
   - Value: the current backend tunnel URL, e.g.
     `https://xxxxx.trycloudflare.com` (Quick Tunnel, temporary) or the
     stable named-tunnel hostname once one exists (see
     `docs/LOCAL_PRODUCTION_DEPLOYMENT.md`).
5. Save. Set it for both **Production** and **Preview** environments (they
   can point at the same or different backend URLs).

**Never commit an actual tunnel URL to this repository.** `wrangler.toml`
intentionally does not set `BACKEND_API_URL` -- it is dashboard-only,
because:
- A Quick Tunnel URL changes every time the tunnel restarts.
- Even the stable named-tunnel hostname shouldn't need a code deploy to
  rotate.

## Updating the URL when the Quick Tunnel restarts

Every time `.\infra\windows\start_backend.ps1 -IncludeQuickTunnel` is run, a
**new** random URL is generated. Two ways to get `BACKEND_API_URL` updated:

- **Automatic (recommended):** configure `CLOUDFLARE_API_TOKEN` and
  `CLOUDFLARE_ACCOUNT_ID` once (see `docs/QUICK_TUNNEL_TESTING.md` step 0).
  `start_backend.ps1 -IncludeQuickTunnel` then calls
  `infra/windows/sync_worker_backend_url.py`, which redeploys
  `frontend/worker.js` unchanged via the Workers API with only the
  `BACKEND_API_URL` binding updated (`keep_assets: true`, so static files
  aren't re-uploaded). This writes the binding directly onto the live
  deployed version. This distinction matters: this project was previously
  hit by dashboard-set Variables not reliably reaching the Production
  environment of a Git-connected ("Workers Builds") Worker -- the API-based
  redeploy sidesteps that entirely by setting the binding on the actual
  version that's live, not on a separate "Variables" record whose
  propagation timing is opaque.
- **Manual:** copy the new URL from the `cloudflared-quick` logs and paste
  it into `BACKEND_API_URL` in the dashboard (step 4 above).

## Health verification (after `BACKEND_API_URL` is set)

- `https://scout.apexora.workers.dev/api/healthz` -> `200`,
  `{"status":"ok",...}`
- `https://scout.apexora.workers.dev/api/readyz` -> `200`,
  `{"status":"ready","database":"ok","cache":"ok"}`
- `https://scout.apexora.workers.dev/` -> frontend loads, no demo banner
  (the demo banner only appears when `probeApi()`'s `/api/healthz` call
  fails).

## Security notes

- The backend's own CORS configuration (`CORS_ORIGINS=https://scout.apexora.workers.dev`,
  no wildcard) is unchanged and still applies for direct backend access
  (e.g. hitting the tunnel URL directly while testing) -- this proxy does
  not replace it, and browsers calling the Worker same-origin don't need
  CORS at all.
- `BACKEND_API_URL` is a Worker **Variable**, not a **Secret**, because the
  tunnel URL itself is not sensitive (it's already visible in
  `cloudflared` logs and, until now, was directly reachable by anyone who
  had it). What matters is that the browser never learns it from
  JavaScript source, `config.js`, or any response body/header -- and this
  Worker never includes it in a client-facing response.
