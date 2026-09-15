# Glassdoor Proxy

Small Flask service that fetches Glassdoor search results using
[`curl_cffi`](https://github.com/lexiforest/curl_cffi)'s Chrome TLS
impersonation — the one thing that's ever actually gotten past Glassdoor's
TLS/JA3 fingerprint block in this project (see `../GLASSDOOR_SETUP.md`).

This needs a real Python process with a compiled dependency, so it can't
run on Cloudflare Workers or Deno Deploy — deploy it on
[Render.com](https://render.com)'s free tier instead (no credit card
required to sign up).

## Deploy

1. Push this repo to GitHub (if not already) so Render can connect to it.
2. Sign up / log in at [dashboard.render.com](https://dashboard.render.com)
   — GitHub login is fastest.
3. **New → Web Service**, connect the `Scout` repo.
4. Settings:
   - **Root Directory:** `glassdoor-proxy`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Instance Type:** Free
5. Add an environment variable:
   - **Key:** `PROXY_KEY`
   - **Value:** `f3e237e95091bdd6664a3967f1ce9b363efdca5c9f2885c5`
     (or your own random string — just make sure it matches what you set
     for `GLASSDOOR_PROXY_KEY` on the Worker)
6. **Create Web Service.** Render gives you a URL like
   `https://glassdoor-proxy-xxxx.onrender.com`.
7. On the Worker:
   ```bash
   cd E:\Scout\worker
   npx wrangler secret put GLASSDOOR_PROXY_URL   # the onrender.com URL
   npx wrangler secret put GLASSDOOR_PROXY_KEY   # f3e237e95091bdd6664a3967f1ce9b363efdca5c9f2885c5
   ```

## Known tradeoff: free-tier cold starts

Render's free web services spin down after ~15 minutes of no traffic, and
take 30-60s to wake back up on the next request. The Worker's timeout for
this call won't wait that long, so **the first search after a period of
inactivity will likely fail for Glassdoor specifically** (falling back to
the still-blocked direct request, so Glassdoor returns 0 for that one
search) — then subsequent searches within the active window will succeed
normally once the service is warm. This is an inherent free-tier
limitation, not a bug.

## Local test

```bash
pip install -r requirements.txt
PROXY_KEY=test123 python app.py
curl "http://localhost:8000/glassdoor?query=python+developer&location=bengaluru" \
  -H "x-proxy-key: test123"
```
