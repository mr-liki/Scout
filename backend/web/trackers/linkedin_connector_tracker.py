"""
linkedin_connector_tracker.py - LinkedIn service layer for SCOUT Jobs.

Wraps the standalone linkedin_connector.py and normalizes results into
the canonical SCOUT job format expected by the frontend:
    {id, title, company, location, link, posted_date, source, ...}

Supports:
    - Search with freshness, under_10, easy_apply filters
    - Lazy detail loading
    - Partial/failed status preservation
    - Resume metadata
"""

import hashlib
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to path for linkedin_connector import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import linkedin_connector as lc

logger = logging.getLogger("scoutjobs.linkedin")

# LinkedIn search parameter bounds
DEFAULT_MAX_JOBS = 50
MAX_MAX_JOBS = 500
DEFAULT_MAX_PAGES = 20
MAX_MAX_PAGES = 100

# Valid sort modes
VALID_SORT_MODES = {"newest", "relevance"}


def _generate_job_id(job: Dict) -> str:
    """Generate stable canonical ID: linkedin:<job_id>."""
    provider_id = job.get("job_id") or job.get("provider_job_id") or ""
    if provider_id:
        return f"linkedin:{provider_id}"
    # Fallback: hash from link or title+company
    link = job.get("link") or job.get("job_url") or ""
    if link:
        return hashlib.md5(link.encode("utf-8")).hexdigest()[:16]
    raw = f"linkedin|{job.get('title', '')}|{job.get('company', '')}|{job.get('location', '')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def normalize_linkedin_job(connector_job: Dict) -> Dict:
    """
    Map a linkedin_connector job dict into the canonical SCOUT format.

    SCOUT canonical fields:
        id, title, company, location, link, posted_date, source,
        salary, easy_apply, early_applicant, remote

    LinkedIn-specific metadata preserved in provider_metadata.
    """
    job_url = connector_job.get("job_url") or ""
    company_url = connector_job.get("company_url") or ""

    # Canonical job
    normalized = {
        "id": _generate_job_id(connector_job),
        "title": connector_job.get("title") or "Untitled",
        "company": connector_job.get("company") or "",
        "location": connector_job.get("location") or "",
        "link": job_url,
        "posted_date": connector_job.get("posted_date") or "",
        "source": "LinkedIn",
        "salary": "",  # LinkedIn guest doesn't provide salary
        "easy_apply": bool(connector_job.get("easy_apply_filter_matched")),
        "early_applicant": bool(connector_job.get("under_10_filter_matched")),
        "remote": bool(
            connector_job.get("location") and
            "remote" in (connector_job.get("location") or "").lower()
        ),
    }

    # LinkedIn-specific metadata
    normalized["provider_metadata"] = {
        "provider": "linkedin",
        "provider_job_id": connector_job.get("job_id"),
        "posted": connector_job.get("posted"),
        "posted_age_minutes": connector_job.get("posted_age_minutes"),
        "freshness_filter_passed": connector_job.get("freshness_filter_passed"),
        "freshness_exact": connector_job.get("freshness_exact", False),
        "freshness_basis": connector_job.get("freshness_basis"),
        "freshness_observed_at": connector_job.get("freshness_observed_at"),
        "freshness_observed_age_seconds": connector_job.get(
            "freshness_observed_age_seconds"
        ),
        "freshness_age_estimate_seconds_at_check": connector_job.get(
            "freshness_age_estimate_seconds_at_check"
        ),
        "linkedin_badge": connector_job.get("linkedin_badge"),
        "under_10_filter_requested": connector_job.get(
            "under_10_filter_requested", False
        ),
        "under_10_filter_matched": connector_job.get(
            "under_10_filter_matched"
        ),
        "under_10_filter_source": connector_job.get("under_10_filter_source"),
        "under_10_applicants": connector_job.get("under_10_applicants"),
        "under_10_exact_count_verified": connector_job.get(
            "under_10_exact_count_verified", False
        ),
        "easy_apply_filter_requested": connector_job.get(
            "easy_apply_filter_requested", False
        ),
        "easy_apply_filter_matched": connector_job.get(
            "easy_apply_filter_matched"
        ),
        "company_url": company_url,
        "company_logo": connector_job.get("company_logo"),
        "linkedin_row": connector_job.get("linkedin_row"),
    }

    # Preserve description if already loaded (from detail)
    if connector_job.get("description"):
        normalized["description"] = connector_job["description"]
    if connector_job.get("applicants"):
        normalized["applicants"] = connector_job["applicants"]
    if connector_job.get("seniority_level"):
        normalized["seniority_level"] = connector_job["seniority_level"]
    if connector_job.get("employment_type"):
        normalized["employment_type"] = connector_job["employment_type"]
    if connector_job.get("job_function"):
        normalized["job_function"] = connector_job["job_function"]
    if connector_job.get("industries"):
        normalized["industries"] = connector_job["industries"]

    return normalized


def normalize_search_response(
    connector_result: Dict,
) -> Dict:
    """
    Convert the full fetch_linkedin_jobs() response into a SCOUT-compatible
    API response.

    Preserves search_status, resume, circuit_breaker metadata.
    """
    jobs = [
        normalize_linkedin_job(j) for j in connector_result.get("jobs", [])
    ]

    return {
        "source": "linkedin",
        "search_status": connector_result.get("search_status"),
        "search_complete": connector_result.get("search_complete", False),
        "stop_reason": connector_result.get("stop_reason"),
        "zero_conclusive": connector_result.get("zero_conclusive", False),
        "total_jobs": connector_result.get("total_jobs", len(jobs)),
        "search_results_found": connector_result.get("search_results_found", 0),
        "expired_before_output": connector_result.get("expired_before_output", 0),
        "jobs": jobs,
        "resume": connector_result.get("resume", {
            "available": False,
            "start": None,
            "linkedin_page": None,
            "reason": None,
        }),
        "circuit_breaker": connector_result.get("circuit_breaker", {
            "opened": False,
            "reason": None,
        }),
        "linkedin_filters": connector_result.get("linkedin_filters", {}),
        "freshness_policy": connector_result.get("freshness_policy"),
        "under_10_policy": connector_result.get("under_10_policy"),
        "rate_limit_summary": {
            "rate_limit_events": connector_result.get(
                "rate_limit_policy", {}
            ).get("rate_limit_events", 0),
            "soft_limit_events": connector_result.get(
                "rate_limit_policy", {}
            ).get("soft_limit_events", 0),
            "soft_limit_recoveries": connector_result.get(
                "rate_limit_policy", {}
            ).get("soft_limit_recoveries", 0),
            "circuit_breaker_opened": connector_result.get(
                "circuit_breaker", {}
            ).get("opened", False),
        },
    }


def search_linkedin(
    keywords: str,
    location: str = "",
    posted_within: Optional[str] = None,
    under_10: bool = False,
    easy_apply: bool = False,
    sort_mode: str = "newest",
    max_jobs: int = DEFAULT_MAX_JOBS,
    max_pages: int = DEFAULT_MAX_PAGES,
    start: int = 0,
) -> Dict:
    """
    High-level LinkedIn search entry point.

    Validates parameters, calls fetch_linkedin_jobs(), normalizes output.
    Returns SCOUT-compatible response with search status preserved.
    """
    t0 = time.time()

    # Validate and clamp
    keywords = (keywords or "").strip()
    if not keywords:
        return {
            "source": "linkedin",
            "search_status": "failed",
            "search_complete": False,
            "stop_reason": "validation_error",
            "zero_conclusive": False,
            "total_jobs": 0,
            "jobs": [],
            "resume": {"available": False},
            "circuit_breaker": {"opened": False},
            "error": "keywords is required",
        }

    location = (location or "").strip()
    sort_mode = sort_mode if sort_mode in VALID_SORT_MODES else "newest"
    max_jobs = max(1, min(max_jobs, MAX_MAX_JOBS))
    max_pages = max(1, min(max_pages, MAX_MAX_PAGES))

    # Validate start
    try:
        start = lc.validate_start_offset(start)
    except ValueError as e:
        return {
            "source": "linkedin",
            "search_status": "failed",
            "search_complete": False,
            "stop_reason": "validation_error",
            "zero_conclusive": False,
            "total_jobs": 0,
            "jobs": [],
            "resume": {"available": False},
            "circuit_breaker": {"opened": False},
            "error": str(e),
        }

    logger.info(
        "LinkedIn search: keywords=%r location=%r posted_within=%r "
        "under_10=%s easy_apply=%s sort=%s limit=%d start=%d",
        keywords, location, posted_within, under_10, easy_apply,
        sort_mode, max_jobs, start,
    )

    try:
        connector_result = lc.fetch_linkedin_jobs(
            keywords=keywords,
            location=location,
            max_jobs=max_jobs,
            posted_within=posted_within,
            under_10=under_10,
            easy_apply=easy_apply,
            sort_mode=sort_mode,
            fetch_details=False,  # NEVER fetch details in feed search
            max_pages=max_pages,
            start=start,
        )
    except lc.LinkedInRateLimited as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning("LinkedIn rate limited: %s", e)
        return {
            "source": "linkedin",
            "search_status": "failed",
            "search_complete": False,
            "stop_reason": "rate_limited",
            "zero_conclusive": False,
            "total_jobs": 0,
            "jobs": [],
            "resume": {"available": False},
            "circuit_breaker": {"opened": True, "reason": "rate_limited"},
            "error": str(e),
            "request_duration_ms": elapsed_ms,
        }
    except lc.LinkedInError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error("LinkedIn error: %s: %s", type(e).__name__, e)
        return {
            "source": "linkedin",
            "search_status": "failed",
            "search_complete": False,
            "stop_reason": "upstream_error",
            "zero_conclusive": False,
            "total_jobs": 0,
            "jobs": [],
            "resume": {"available": False},
            "circuit_breaker": {"opened": False},
            "error": f"{type(e).__name__}: {e}",
            "request_duration_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.exception("Unexpected LinkedIn error")
        return {
            "source": "linkedin",
            "search_status": "failed",
            "search_complete": False,
            "stop_reason": "internal_error",
            "zero_conclusive": False,
            "total_jobs": 0,
            "jobs": [],
            "resume": {"available": False},
            "circuit_breaker": {"opened": False},
            "error": "Internal error",
            "request_duration_ms": elapsed_ms,
        }

    elapsed_ms = int((time.time() - t0) * 1000)
    result = normalize_search_response(connector_result)
    result["request_duration_ms"] = elapsed_ms

    logger.info(
        "LinkedIn search complete: status=%s stop=%s jobs=%d duration=%dms",
        result.get("search_status"),
        result.get("stop_reason"),
        result.get("total_jobs", 0),
        elapsed_ms,
    )

    return result


def fetch_detail(job_id: str) -> Dict:
    """
    Lazy detail fetch for a single LinkedIn job.

    Uses the connector's public detail functions.
    Returns SCOUT-compatible detail response.
    """
    # Validate job_id: must be numeric
    if not job_id or not str(job_id).isdigit():
        return {
            "source": "linkedin",
            "provider_job_id": job_id,
            "upstream_status": "invalid_id",
            "error": f"Invalid LinkedIn job ID: {job_id}",
        }

    t0 = time.time()

    try:
        session = lc.create_session(
            rate_min_interval=1.0,
            rate_max_interval=10.0,
        )
        detail_html_cache = {}

        payload = lc.fetch_detail_html(
            session=session,
            job_id=str(job_id),
            detail_html_cache=detail_html_cache,
            attempts=2,
        )

        detail = lc.parse_job_detail(
            payload["html"],
            fallback_job_id=str(job_id),
            observed_at_epoch=payload["fetched_at_epoch"],
        )

        # Apply under-10 evidence if available
        if detail.get("applicant_count") is not None:
            detail = lc.apply_under_10_evidence(detail, under_10_requested=False)

        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "source": "linkedin",
            "provider_job_id": str(job_id),
            "upstream_status": "success",
            "title": detail.get("title"),
            "company": detail.get("company"),
            "location": detail.get("location"),
            "posted": detail.get("posted"),
            "posted_date": detail.get("posted_date"),
            "description": detail.get("description"),
            "applicants": detail.get("applicants"),
            "applicant_count": detail.get("applicant_count"),
            "applicant_count_exact": detail.get("applicant_count_exact"),
            "applicant_count_minimum": detail.get("applicant_count_minimum"),
            "applicant_count_relation": detail.get("applicant_count_relation"),
            "seniority_level": detail.get("seniority_level"),
            "employment_type": detail.get("employment_type"),
            "job_function": detail.get("job_function"),
            "industries": detail.get("industries"),
            "job_url": detail.get("job_url"),
            "company_url": detail.get("company_url"),
            "company_logo": detail.get("company_logo"),
            "freshness_basis": detail.get("freshness_basis"),
            "freshness_exact": detail.get("freshness_exact", False),
            "request_duration_ms": elapsed_ms,
        }

    except lc.LinkedInRateLimited as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning("LinkedIn detail rate limited for %s: %s", job_id, e)
        return {
            "source": "linkedin",
            "provider_job_id": str(job_id),
            "upstream_status": "rate_limited",
            "error": str(e),
            "request_duration_ms": elapsed_ms,
        }
    except lc.LinkedInError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning("LinkedIn detail error for %s: %s", job_id, e)
        return {
            "source": "linkedin",
            "provider_job_id": str(job_id),
            "upstream_status": "unavailable",
            "error": str(e),
            "request_duration_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.exception("Unexpected error fetching LinkedIn detail %s", job_id)
        return {
            "source": "linkedin",
            "provider_job_id": str(job_id),
            "upstream_status": "error",
            "error": "Internal error fetching detail",
            "request_duration_ms": elapsed_ms,
        }
    finally:
        try:
            session.close()
        except Exception:
            pass
