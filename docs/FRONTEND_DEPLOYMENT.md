# SCOUTJOBS Frontend Deployment Guide

> **NOTE:** The live frontend is deployed as **Cloudflare Workers Static
> Assets** at `https://scout.apexora.workers.dev` (GitHub `main` ->
> automatic Cloudflare deployment), not Cloudflare Pages. The general
> concepts below (static files, no build step, configurable `apiBase`)
> still apply; see
> [`docs/LOCAL_PRODUCTION_DEPLOYMENT.md`](LOCAL_PRODUCTION_DEPLOYMENT.md)
> for how the backend URL is connected once the Cloudflare Tunnel exists.

## Cloudflare Pages Deployment

The SCOUTJOBS frontend is a **static HTML/CSS/JS application** with no build step required.

## 1. Architecture Overview

```
GitHub Repository
       |
       v
Cloudflare Pages
       |
       v
SCOUTJOBS Frontend (static files)
       |
       v
API requests → https://api.<YOUR_DOMAIN>
                      |
                      v
              Cloudflare Tunnel
                      |
                      v
              FastAPI Backend
```

## 2. Cloudflare Pages Settings

### Repository Connection

1. Log into [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Go to **Pages** → **Create a project**
3. Select **Connect to Git**
4. Select **GitHub**
5. Authorize Cloudflare to access your repository
6. Select repository: `mr-liki/Scout`

### Build Settings

| Setting | Value |
|---------|-------|
| **Production branch** | `main` |
| **Framework preset** | `None` |
| **Build command** | *(leave empty)* |
| **Build output directory** | `frontend` |
| **Root directory** | `frontend` |

**Important**: Do NOT set a build command. The frontend is pure static files with no compilation step.

### Environment Variables

No environment variables are required for the frontend build.

## 3. API Base Configuration

The frontend uses a configurable API base URL stored in:

```
frontend/js/api.js
```

### Configuration Method

```javascript
// Set API base URL
import { setApiBase } from "./api.js";

// For production
setApiBase("https://api.your-domain.com");

// For local development
setApiBase("http://localhost:8000");

// For same-origin (default)
setApiBase("");
```

### Current Default

The frontend defaults to same-origin API requests. When deployed to Cloudflare Pages, API requests will go to the Pages domain unless explicitly configured.

### Production Configuration

For production, set the API base to your Cloudflare Tunnel endpoint:

```javascript
setApiBase("https://api.your-domain.com");
```

This can be done by:
1. Editing `frontend/js/api.js` before pushing, OR
2. Using a configuration file (see below)

### Optional: Configuration File

Create `frontend/config.js` for easier environment switching:

```javascript
// frontend/config.js
window.SCOUTJOBS_CONFIG = {
  apiBase: "https://api.your-domain.com"
};
```

Then in `index.html`, add before the main script:

```html
<script src="config.js"></script>
```

And in `api.js`, read from config:

```javascript
let _apiBase = window.SCOUTJOBS_CONFIG?.apiBase || "";
```

## 4. GitHub Deployment Flow

### Developer Workflow

```
1. Edit frontend code locally
2. git add frontend/
3. git commit -m "Update frontend"
4. git push origin main
```

### Cloudflare Pages Automatic Build

```
GitHub push
    ↓
Cloudflare Pages webhook
    ↓
Cloudflare Pages build (no build step)
    ↓
Static files deployed
    ↓
New version live at https://<project>.pages.dev
```

### No Manual Upload Required

The deployment is fully automatic. Every push to `main` triggers a new deployment.

## 5. Custom Domain Setup

### Option A: Use Cloudflare Pages Default URL

Your site will be available at:
```
https://<project-name>.pages.dev
```

### Option B: Custom Domain

1. In Cloudflare Pages, go to **Custom domains**
2. Add your domain (e.g., `jobs.your-domain.com`)
3. Cloudflare automatically configures DNS
4. SSL certificate is provisioned automatically

### Option C: Apex Domain

For root domain (e.g., `your-domain.com`):
1. Add custom domain in Pages
2. Cloudflare handles DNS and SSL

## 6. Local Development

### Option 1: Direct File Open

Open `frontend/index.html` in your browser.

**Note**: Some browsers block ES module imports from `file://` protocol. Use a local server instead.

### Option 2: Python HTTP Server

```bash
cd frontend
python -m http.server 8080
```

Then open: `http://localhost:8080`

### Option 3: Node.js HTTP Server

```bash
npx serve frontend
```

### Local API Configuration

For local development with a running backend:

```javascript
// In frontend/js/api.js
setApiBase("http://localhost:8000");
```

Or create `frontend/config.js`:

```javascript
window.SCOUTJOBS_CONFIG = {
  apiBase: "http://localhost:8000"
};
```

## 7. Frontend Structure

```
frontend/
├── index.html          # Entry point
├── css/
│   └── styles.css      # All styles
├── js/
│   ├── main.js         # App bootstrap
│   ├── api.js          # API communication
│   ├── ui.js           # UI components
│   ├── store.js        # LocalStorage persistence
│   └── demo.js         # Demo data fallback
├── config.js           # (optional) API configuration
└── preview.html        # Preview page
```

## 8. Deployment Checklist

- [ ] Cloudflare Pages connected to GitHub
- [ ] Build settings configured (no build command, output: frontend)
- [ ] API base configured for production
- [ ] Custom domain configured (optional)
- [ ] Local development tested
- [ ] Push to main triggers deployment

## 9. Troubleshooting

### API Not Reachable

1. Check API base configuration
2. Verify Cloudflare Tunnel is running
3. Test API directly: `curl https://api.your-domain.com/healthz`

### Static Assets Not Loading

1. Verify build output directory is `frontend`
2. Check browser console for 404 errors
3. Verify file paths are relative

### CORS Errors

1. Check backend CORS configuration
2. Verify `ALLOWED_ORIGINS` includes your Pages domain

## 10. Rollback

To rollback a deployment:
1. Go to Cloudflare Pages → Deployments
2. Find the previous deployment
3. Click "Rollback to this deployment"

## 11. Monitoring

Cloudflare Pages provides:
- Deployment status
- Build logs
- Analytics (visitors, requests, bandwidth)

Access via Cloudflare Dashboard → Pages → Your project.

## 12. Cost

**Cloudflare Pages Free Tier includes:**
- Unlimited deployments
- 500 builds per month
- 100 GB bandwidth per month
- Unlimited requests

This is sufficient for SCOUTJOBS production use.
