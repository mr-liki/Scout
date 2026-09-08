"""
LinkedIn background worker for SCOUTJOBS production.

Runs exactly ONE worker initially.
Calls existing fetch_linkedin_jobs(fetch_details=False).
Preserves all connector metadata.
Implements stale-running reconciliation on startup.
"""

import logging
import sys
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from db.session import get_sync_session
from db.models import Search, Job, SearchJob, JobDetail
from db.cache import CacheManager
from worker.linkedin_service import normalize_linkedin_job
from backend.api.config import get_settings
import linkedin_connector as lc

logger = logging.getLogger("scoutjobs.worker")


def reconcile_stale_searches():
    """
    On worker startup, detect searches stuck in 'running' for too long.

    Transitions stale searches to recoverable states:
    - partial if jobs exist
    - failed if no jobs exist

    Preserves resume.start exactly.
    """
    settings = get_settings()
    session = get_sync_session()

    try:
        stale_threshold = datetime.now(timezone.utc) - timedelta(
            seconds=settings.SEARCH_STALE_AFTER_SECONDS
        )

        # Find searches stuck in 'running'
        stale_searches = session.query(Search).filter(
            Search.status == "running",
            Search.started_at < stale_threshold,
        ).all()

        for search in stale_searches:
            # Check if any jobs were persisted
            job_count = session.query(SearchJob).filter(
                SearchJob.search_id == search.id
            ).count()

            if job_count > 0:
                search.status = "partial"
                search.stop_reason = "worker_interrupted"
                search.error_message = "Search was interrupted during worker restart"
            else:
                search.status = "failed"
                search.stop_reason = "worker_interrupted"
                search.error_message = "Search was interrupted during worker restart with no results"

            search.finished_at = datetime.now(timezone.utc)
            logger.warning(
                "Reconciled stale search %s: status=%s jobs=%d",
                search.id, search.status, job_count
            )

        session.commit()

        if stale_searches:
            logger.info("Reconciled %d stale searches", len(stale_searches))

    except Exception as e:
        logger.exception("Failed to reconcile stale searches")
        session.rollback()
    finally:
        session.close()


def run_linkedin_search(search_id: str) -> Dict:
    """
    Execute LinkedIn search in background worker.

    Args:
        search_id: UUID of the search record

    Returns:
        Dict with search status and results
    """
    session = get_sync_session()
    cache = CacheManager()

    try:
        # Load search record
        search = session.query(Search).filter(Search.id == search_id).first()
        if not search:
            logger.error("Search %s not found", search_id)
            return {"error": "Search not found"}

        # Mark as running
        search.status = "running"
        search.started_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            "Starting LinkedIn search %s: keywords=%r location=%r start=%d",
            search_id, search.keywords, search.location, search.start_offset
        )

        # Call existing connector
        t0 = time.time()
        try:
            connector_result = lc.fetch_linkedin_jobs(
                keywords=search.keywords,
                location=search.location or "",
                max_jobs=search.max_jobs,
                posted_within=search.posted_within,
                under_10=search.under_10,
                easy_apply=search.easy_apply,
                sort_mode=search.sort_mode,
                fetch_details=False,  # NEVER fetch details in feed search
                max_pages=search.max_pages,
                start=search.start_offset,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            logger.error("LinkedIn search failed: %s", e)

            search.status = "failed"
            search.error_message = str(e)
            search.stop_reason = "upstream_error"
            search.finished_at = datetime.now(timezone.utc)
            session.commit()

            return {
                "search_id": str(search_id),
                "status": "failed",
                "error": str(e),
                "duration_ms": elapsed_ms,
            }

        elapsed_ms = int((time.time() - t0) * 1000)

        # Update search record with results
        search.status = connector_result.get("search_status", "failed")
        search.search_complete = connector_result.get("search_complete", False)
        search.stop_reason = connector_result.get("stop_reason")
        search.zero_conclusive = connector_result.get("zero_conclusive", False)

        # Resume
        resume = connector_result.get("resume", {})
        search.resume_available = resume.get("available", False)
        search.resume_start = resume.get("start")
        search.resume_linkedin_page = resume.get("linkedin_page")
        search.resume_reason = resume.get("reason")

        # Circuit breaker
        cb = connector_result.get("circuit_breaker", {})
        search.circuit_breaker_opened = cb.get("opened", False)
        search.circuit_breaker_reason = cb.get("reason")
        search.circuit_breaker_failed_start = cb.get("failed_start")
        search.circuit_breaker_failed_page = cb.get("failed_page")

        # Store full connector metadata
        search.connector_metadata = {
            "linkedin_filters": connector_result.get("linkedin_filters"),
            "freshness_policy": connector_result.get("freshness_policy"),
            "under_10_policy": connector_result.get("under_10_policy"),
            "rate_limit_summary": {
                "rate_limit_events": connector_result.get("rate_limit_policy", {}).get("rate_limit_events", 0),
                "soft_limit_events": connector_result.get("rate_limit_policy", {}).get("soft_limit_events", 0),
                "soft_limit_recoveries": connector_result.get("rate_limit_policy", {}).get("soft_limit_recoveries", 0),
            },
            "expired_before_output": connector_result.get("expired_before_output", 0),
            "search_results_found": connector_result.get("search_results_found", 0),
            "duration_ms": elapsed_ms,
        }

        search.finished_at = datetime.now(timezone.utc)

        # Persist jobs
        jobs = connector_result.get("jobs", [])
        position = 0
        for connector_job in jobs:
            position += 1
            normalized = normalize_linkedin_job(connector_job)

            # Upsert job
            existing_job = session.query(Job).filter(
                Job.source == "linkedin",
                Job.provider_job_id == normalized["provider_job_id"],
            ).first()

            if existing_job:
                # Update existing
                existing_job.last_seen_at = datetime.now(timezone.utc)
                existing_job.provider_metadata = normalized["provider_metadata"]
                job_id = existing_job.id
            else:
                # Create new
                new_job = Job(
                    source="linkedin",
                    provider_job_id=normalized["provider_job_id"],
                    title=normalized["title"],
                    company=normalized["company"],
                    location=normalized["location"],
                    link=normalized["link"],
                    posted_date=normalized["posted_date"],
                    salary=normalized.get("salary", ""),
                    easy_apply=normalized["easy_apply"],
                    early_applicant=normalized["early_applicant"],
                    remote=normalized["remote"],
                    provider_metadata=normalized["provider_metadata"],
                )
                session.add(new_job)
                session.flush()
                job_id = new_job.id

            # Link search to job
            search_job = SearchJob(
                search_id=search.id,
                job_id=job_id,
                position=position,
            )
            session.add(search_job)

        session.commit()

        logger.info(
            "LinkedIn search %s complete: status=%s jobs=%d duration=%dms",
            search_id, search.status, len(jobs), elapsed_ms
        )

        # Cache result
        cache.cache_search_result(
            search.query_hash,
            {"search_id": str(search_id), "status": search.status},
        )

        return {
            "search_id": str(search_id),
            "status": search.status,
            "jobs_found": len(jobs),
            "duration_ms": elapsed_ms,
        }

    except Exception as e:
        logger.exception("Unexpected error in worker for search %s", search_id)
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()
        cache.close()
