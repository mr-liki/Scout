"""
LinkedIn service layer for SCOUTJOBS production.

Normalizes connector output to canonical job format.
Provides detail fetching with caching.
"""

import hashlib
import logging
import sys
import os
import time
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import linkedin_connector as lc
from db.cache import CacheManager

logger = logging.getLogger("scoutjobs.linkedin")


def _generate_job_id(connector_job: Dict) -> str:
    """Generate stable provider_job_id from connector output."""
    provider_id = connector_job.get("job_id") or ""
    if provider_id:
        return provider_id
    # Fallback: hash from link
    link = connector_job.get("job_url") or ""
    if link:
        return hashlib.md5(link.encode("utf-8")).hexdigest()[:16]
    return hashlib.md5(
        f"{connector_job.get('title', '')}|{connector_job.get('company', '')}".encode()
    ).hexdigest()[:16]


def normalize_linkedin_job(connector_job: Dict) -> Dict:
    """
    Map connector job to canonical SCOUTJOBS format.

    Returns dict with:
        - provider_job_id (stable identifier)
        - canonical fields (title, company, etc.)
        - provider_metadata (LinkedIn-specific)
    """
    job_url = connector_job.get("job_url") or ""
    company_url = connector_job.get("company_url") or ""

    return {
        "provider_job_id": _generate_job_id(connector_job),
        "title": connector_job.get("title") or "Untitled",
        "company": connector_job.get("company") or "",
        "location": connector_job.get("location") or "",
        "link": job_url,
        "posted_date": connector_job.get("posted_date") or "",
        "salary": "",
        "easy_apply": bool(connector_job.get("easy_apply_filter_matched")),
        "early_applicant": bool(connector_job.get("under_10_filter_matched")),
        "remote": bool(
            connector_job.get("location") and
            "remote" in (connector_job.get("location") or "").lower()
        ),
        "provider_metadata": {
            "provider": "linkedin",
            "provider_job_id": connector_job.get("job_id"),
            "posted": connector_job.get("posted"),
            "posted_age_minutes": connector_job.get("posted_age_minutes"),
            "freshness_filter_passed": connector_job.get("freshness_filter_passed"),
            "freshness_exact": connector_job.get("freshness_exact", False),
            "freshness_basis": connector_job.get("freshness_basis"),
            "freshness_observed_at": connector_job.get("freshness_observed_at"),
            "freshness_observed_age_seconds": connector_job.get("freshness_observed_age_seconds"),
            "linkedin_badge": connector_job.get("linkedin_badge"),
            "under_10_filter_requested": connector_job.get("under_10_filter_requested", False),
            "under_10_filter_matched": connector_job.get("under_10_filter_matched"),
            "under_10_filter_source": connector_job.get("under_10_filter_source"),
            "under_10_applicants": connector_job.get("under_10_applicants"),
            "under_10_exact_count_verified": connector_job.get("under_10_exact_count_verified", False),
            "easy_apply_filter_requested": connector_job.get("easy_apply_filter_requested", False),
            "easy_apply_filter_matched": connector_job.get("easy_apply_filter_matched"),
            "company_url": company_url,
            "company_logo": connector_job.get("company_logo"),
        },
    }


def fetch_linkedin_job_detail(
    job_id: str,
    cache: Optional[CacheManager] = None,
) -> Dict:
    """
    Lazy detail fetch for a single LinkedIn job.

    Uses cache if available.
    Returns normalized detail response.
    """
    # Check cache first
    if cache:
        cached = cache.get_cached_job_detail(job_id)
        if cached:
            return cached

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

        elapsed_ms = int((time.time() - t0) * 1000)

        result = {
            "provider_job_id": str(job_id),
            "upstream_status": "success",
            "title": detail.get("title"),
            "company": detail.get("company"),
            "location": detail.get("location"),
            "posted": detail.get("posted"),
            "description": detail.get("description"),
            "applicants": detail.get("applicants"),
            "applicant_count": detail.get("applicant_count"),
            "applicant_count_exact": detail.get("applicant_count_exact"),
            "applicant_count_minimum": detail.get("applicant_count_minimum"),
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

        # Cache the result
        if cache:
            cache.cache_job_detail(job_id, result)

        return result

    except lc.LinkedInRateLimited as e:
        return {
            "provider_job_id": str(job_id),
            "upstream_status": "rate_limited",
            "error": str(e),
        }
    except lc.LinkedInError as e:
        return {
            "provider_job_id": str(job_id),
            "upstream_status": "unavailable",
            "error": str(e),
        }
    except Exception as e:
        logger.exception("Error fetching LinkedIn detail %s", job_id)
        return {
            "provider_job_id": str(job_id),
            "upstream_status": "error",
            "error": "Internal error",
        }
    finally:
        try:
            session.close()
        except Exception:
            pass
