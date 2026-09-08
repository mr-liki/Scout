# infra/render

> **STATUS: OPTIONAL ALTERNATIVE DEPLOYMENT -- NOT CURRENT PRODUCTION.**
> Current production is the local self-host stack on the dedicated Windows
> PC via Docker Desktop -- see
> [`docs/LOCAL_PRODUCTION_DEPLOYMENT.md`](../../docs/LOCAL_PRODUCTION_DEPLOYMENT.md).

Render-specific deployment glue. This directory is only used by the optional
cloud (Render + Neon + Upstash) deployment path -- it has no effect on local
Docker Compose / self-host deployment (see `infra/docker-compose.prod.yml`
and `infra/windows/`, which are the current production path).

## Files

- `start_render.py` -- the container's entrypoint on Render (see `render.yaml`
  `dockerCommand`). Runs `alembic upgrade head` (with retry for transient
  Neon connectivity issues), then starts the existing FastAPI app
  (`backend.api.app:app`, one Uvicorn worker, bound to Render's `$PORT`) and
  the existing single LinkedIn RQ worker (`backend.worker.runner`) as two
  child processes. Monitors both: if either exits unexpectedly, it tears
  down the other and exits non-zero so Render restarts the service. Forwards
  SIGTERM/SIGINT to both children for graceful shutdown.
- `.env.render.example` -- placeholder environment variables for reference.
  Real secrets (`DATABASE_URL`, `REDIS_URL`) are entered directly in the
  Render dashboard, never committed.

See [`docs/CLOUD_DEPLOYMENT.md`](../../docs/CLOUD_DEPLOYMENT.md) for the full
setup walkthrough.
