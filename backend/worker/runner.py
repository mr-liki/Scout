"""
RQ Worker runner for SCOUTJOBS LinkedIn background jobs.

Runs exactly ONE worker for LinkedIn concurrency control.
Implements stale-running reconciliation on startup.
Handles graceful shutdown on SIGTERM.
"""

import os
import sys
import signal
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from redis import Redis
from rq import Queue, Worker

from api.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("scoutjobs.worker.runner")


def main():
    settings = get_settings()
    redis_conn = Redis.from_url(settings.REDIS_URL)

    # Reconcile stale searches on startup
    logger.info("Reconciling stale searches...")
    try:
        from worker.linkedin_worker import reconcile_stale_searches
        reconcile_stale_searches()
    except Exception as e:
        logger.error("Failed to reconcile stale searches: %s", e)

    q = Queue(settings.QUEUE_NAME, connection=redis_conn)

    logger.info("Starting LinkedIn worker (concurrency=1)")
    logger.info("Queue: %s", settings.QUEUE_NAME)
    logger.info("Timeout: %d seconds", settings.LINKEDIN_JOB_TIMEOUT_SECONDS)

    worker = Worker([q], connection=redis_conn)

    # Handle SIGTERM gracefully
    def handle_signal(signum, frame):
        logger.info("Received signal %d, shutting down gracefully...", signum)
        worker.handle_executed_job = None  # Prevent new job pickup
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_signal)

    worker.work()


if __name__ == "__main__":
    main()
