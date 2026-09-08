"""
Render supervisor for SCOUTJOBS.

Render Free gives us exactly one web service container, so this process runs
both the FastAPI API and the single LinkedIn RQ worker as child processes:

    1. Run `alembic upgrade head` against Neon (retrying transient failures).
    2. Start `uvicorn backend.api.app:app` bound to Render's $PORT (1 worker).
    3. Start `python -m backend.worker.runner` (exactly one LinkedIn worker).
    4. Monitor both children. If either exits unexpectedly, tear down the
       other and exit non-zero so Render restarts the service.
    5. On SIGTERM/SIGINT, forward shutdown to both children and exit 0.

This script never talks to LinkedIn itself -- it only launches the existing
API and worker processes unchanged.
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.api.config import normalize_database_url  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [render-supervisor] %(levelname)s: %(message)s",
)
logger = logging.getLogger("scoutjobs.render.supervisor")

DEFAULT_PORT = "10000"
MAX_MIGRATION_ATTEMPTS = 8
CHILD_SHUTDOWN_GRACE_SECONDS = 20
MONITOR_POLL_SECONDS = 2


def get_port() -> str:
    """Return the port Render assigns via $PORT, with a local-testing fallback."""
    return os.environ.get("PORT", DEFAULT_PORT)


def require_env(name: str) -> str:
    """Fetch a required environment variable, failing startup loudly if absent."""
    value = os.environ.get(name)
    if not value:
        logger.error("Missing required environment variable: %s", name)
        raise SystemExit(1)
    return value


def build_migration_command() -> list:
    """Command that applies pending Alembic migrations before the app starts."""
    return [
        sys.executable, "-m", "alembic",
        "-c", "backend/db/alembic.ini",
        "upgrade", "head",
    ]


def build_api_command(port: str) -> list:
    """Command that starts the FastAPI app with exactly one Uvicorn worker."""
    return [
        sys.executable, "-m", "uvicorn",
        "backend.api.app:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--workers", "1",
        "--proxy-headers",
        "--forwarded-allow-ips=*",
    ]


def build_worker_command() -> list:
    """Command that starts the single existing LinkedIn RQ worker."""
    return [sys.executable, "-m", "backend.worker.runner"]


def run_migrations_with_retry(max_attempts: int = MAX_MIGRATION_ATTEMPTS) -> None:
    """
    Run `alembic upgrade head`, retrying with backoff for transient Neon
    startup/network failures. Never downgrades or recreates schema -- a
    persistent failure stops startup instead of running against a stale
    schema.
    """
    cmd = build_migration_command()
    for attempt in range(1, max_attempts + 1):
        logger.info("Running database migrations (attempt %d/%d)...", attempt, max_attempts)
        result = subprocess.run(cmd, cwd=str(REPO_ROOT))
        if result.returncode == 0:
            logger.info("Migrations complete")
            return

        if attempt == max_attempts:
            logger.error("Migrations failed after %d attempts, aborting startup", max_attempts)
            raise SystemExit(1)

        delay = attempt * 2
        logger.warning("Migration attempt %d failed (exit %s), retrying in %ds...",
                        attempt, result.returncode, delay)
        time.sleep(delay)


class Supervisor:
    """Owns the API and worker child processes and their lifecycle."""

    def __init__(self):
        self.api_proc = None
        self.worker_proc = None
        self._shutting_down = False

    def start(self, port: str) -> None:
        logger.info("Starting API on port %s", port)
        self.api_proc = subprocess.Popen(build_api_command(port), cwd=str(REPO_ROOT))

        logger.info("Starting one LinkedIn worker")
        self.worker_proc = subprocess.Popen(build_worker_command(), cwd=str(REPO_ROOT))

    @staticmethod
    def _terminate(proc, name: str) -> None:
        if proc is None or proc.poll() is not None:
            return
        logger.info("Sending shutdown signal to %s (pid=%s)...", name, proc.pid)
        try:
            proc.terminate()
        except Exception:
            pass

    @staticmethod
    def _kill(proc, name: str) -> None:
        if proc is None or proc.poll() is not None:
            return
        logger.warning("Force killing %s (pid=%s) after grace period...", name, proc.pid)
        try:
            proc.kill()
        except Exception:
            pass

    def shutdown(self, grace_seconds: int = CHILD_SHUTDOWN_GRACE_SECONDS) -> None:
        """Forward termination to both children, wait, then force kill stragglers."""
        if self._shutting_down:
            return
        self._shutting_down = True

        self._terminate(self.api_proc, "api")
        self._terminate(self.worker_proc, "worker")

        deadline = time.time() + grace_seconds
        for proc in (self.api_proc, self.worker_proc):
            if proc is None:
                continue
            remaining = max(0, deadline - time.time())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                pass

        self._kill(self.api_proc, "api")
        self._kill(self.worker_proc, "worker")

    def monitor(self) -> int:
        """
        Watch both children. If either exits on its own (and shutdown was not
        already requested), tear down the other and return a non-zero code so
        Render restarts the whole service -- an API left running with a dead
        worker (or vice versa) is never an acceptable end state.
        """
        while True:
            if self._shutting_down:
                return 0

            api_code = self.api_proc.poll()
            worker_code = self.worker_proc.poll()

            if api_code is not None:
                logger.error("API process exited unexpectedly with code %s", api_code)
                self.shutdown()
                return api_code if api_code else 1

            if worker_code is not None:
                logger.error("LinkedIn worker process exited unexpectedly with code %s", worker_code)
                self.shutdown()
                return worker_code if worker_code else 1

            time.sleep(MONITOR_POLL_SECONDS)


def main() -> None:
    environment = os.environ.get("ENVIRONMENT", "development")
    logger.info("SCOUTJOBS Render startup")
    logger.info("Environment: %s", environment)

    database_url = require_env("DATABASE_URL")
    require_env("REDIS_URL")
    logger.info("Database configured: yes")
    logger.info("Redis configured: yes")

    # Normalize once and export so alembic + API + worker all see the same
    # psycopg3-compatible URL, without ever logging its contents.
    os.environ["DATABASE_URL"] = normalize_database_url(database_url)

    run_migrations_with_retry()

    supervisor = Supervisor()
    supervisor.start(get_port())

    def handle_signal(signum, _frame):
        logger.info("Received signal %s, shutting down gracefully...", signum)
        supervisor.shutdown()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    sys.exit(supervisor.monitor())


if __name__ == "__main__":
    main()
