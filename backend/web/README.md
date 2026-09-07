# ⚡ SCOUT Jobs

**Every job board. One search.**

A production-ready, all-in-one job search website that queries **LinkedIn,
Indeed, Glassdoor and Wellfound** in parallel — free, no accounts, no API keys.

- 🎯 One search across 4 job platforms, merged & de-duplicated
- 💰 Salary signals from Glassdoor + Wellfound, early-applicant flags from LinkedIn
- 📌 Saved jobs (stored in your browser), dark/light themes, fully responsive
- 🚀 Zero build step — plain HTML/CSS/JS, deploys to any static host
- 🐍 Python API reusing the battle-tested SCOUT trackers (serverless-ready)

---

## 🚀 Quick start (local)

Run these from `backend/web/` (this directory) — `server.py` serves the
`frontend/` folder one level up alongside the API, so both must stay in
place relative to each other.

```bash
# 1. Create a venv and install the backend deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Run the WHOLE app (frontend + API) from one process
python server.py
# → http://localhost:8000
```

Try the API directly:
```bash
curl "http://localhost:8000/api/search?q=Python%20Developer&location=Remote"
curl "http://localhost:8000/api/health"
```

---

## ☁️ Host it for FREE

Vercel and Netlify config (`vercel.json`, `netlify.toml`) live at the repo
root, since a deployment needs both `frontend/` and `backend/web/` together.

### Option A — Vercel (recommended, full experience)

1. Push the repo root to GitHub.
2. Go to [vercel.com/new](https://vercel.com/new) → **Import** your repo.
3. Vercel auto-detects `vercel.json` at the repo root. Deploy.

Done. You get the static site **and** the Python API on the free Hobby plan.
The frontend calls `/api/search` automatically (same origin, no CORS setup).

### Option B — Netlify

1. Push to GitHub.
2. Go to [netlify.com](https://netlify.com) → **Add new site** → **Import from Git**.
3. Build settings are read from the repo-root `netlify.toml`
   (publish = `frontend`, functions = `backend/web/netlify-functions`).

### Option C — GitHub Pages (static only)

1. Enable **Pages** → deploy from `frontend/` (or a branch).
2. The site works — but without the API it falls back to **demo data** and
   shows a "Demo mode" banner. Perfect for showcasing the design.

> 💡 For a full experience on GitHub Pages: host the API on Vercel/Netlify
> and change `apiBase` in `js/api.js` to your deployed API URL (CORS is
> enabled on all endpoints).

---

## 🧠 Architecture

```
frontend/
├── index.html              # SPA shell
├── css/styles.css          # design system (light/dark, responsive)
└── js/
    ├── main.js              # entry + router
    ├── ui.js                # templates, rendering, modal, toasts
    ├── api.js               # live API client + demo fallback
    ├── demo.js              # sample dataset (for static hosting)
    └── store.js             # saved jobs + theme (localStorage)

backend/web/
├── trackers/                # the 4 SCOUT job engines (copied from the CLI)
│   ├── engine.py            # concurrent search + dedupe + time budget
│   ├── linkedin_rss_tracker.py
│   ├── indeed_tracker.py
│   ├── glassdoor_tracker.py
│   └── wellfound_tracker.py
├── api/search.py             # Vercel serverless function (Python)
├── netlify-functions/search.py   # Netlify function (Python)
├── server.py                 # local all-in-one server (stdlib only, serves ../../frontend)
└── requirements.txt

vercel.json                   # Vercel config (repo root)
netlify.toml                  # Netlify config (repo root)
```

### How a search works

1. Browser calls `GET /api/search?q=Python Developer&location=Remote`.
2. `trackers/engine.py` launches all 4 trackers **concurrently** under a
   wall-clock budget (default 18s) so one slow platform can't kill the request.
3. Results are merged, de-duplicated (same job on two boards = one result),
   tagged by source, and returned as JSON.
4. The UI renders cards with source badges, salary, remote/early-applicant
   tags, a detail modal, and save buttons.

### Graceful degradation

- If a platform is down or blocked → that platform contributes 0 jobs and the
  rest still work (each tracker never raises).
- If the entire API is unreachable → the frontend falls back to the bundled
  demo dataset with a "Demo mode" banner.

---

## 🔌 API reference

| Endpoint | Params | Description |
|---|---|---|
| `GET /api/search` | `q` (required), `location` (optional) | Search all platforms |
| `GET /api/health` | — | Liveness + service info |

Response:
```json
{
  "query": { "keywords": "Python Developer", "location": "Remote" },
  "total": 27,
  "platforms": { "LinkedIn": 0, "Indeed": 10, "Glassdoor": 10, "Wellfound": 7 },
  "jobs": [
    {
      "id": "…", "title": "…", "company": "…", "location": "…",
      "salary": "$120k – $160k", "posted_date": "2026-08-07",
      "link": "https://…", "source": "Indeed",
      "early_applicant": false, "easy_apply": false, "remote": true,
      "description": "…"
    }
  ],
  "errors": [],
  "searched_at": "…"
}
```

---

## 🧪 Testing

```bash
python server.py &                                  # start
curl "http://localhost:8000/api/health"
curl "http://localhost:8000/api/search?q=Python"
python -m py_compile trackers/engine.py server.py   # syntax check
```

## ⚖️ Honest limitations

- **Indeed** is scoped to the US job index (non-US locations may return fewer).
- **Glassdoor** is fetched via the free r.jina.ai proxy (rate-limited; cached 15 min).
- **Wellfound** sits behind flaky Cloudflare — retries + graceful 0-job fallback.
- **LinkedIn** uses the public guest search; heavy/rapid use can get throttled.
- Sources like **Naukri** are behind aggressive bot protection (Akamai +
  reCAPTCHA) and are deliberately not included.
