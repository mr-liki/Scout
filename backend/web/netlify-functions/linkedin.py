"""
Netlify Python function: /api/jobs/linkedin

Handles LinkedIn-specific search requests with freshness, under_10,
easy_apply, and resume parameters.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trackers.linkedin_connector_tracker import search_linkedin, fetch_detail


def handler(event, context):
    """Netlify function handler."""
    path = event.get("path", "/")
    qs = event.get("queryStringParameters") or {}

    # Detail endpoint: /api/jobs/linkedin/{job_id}
    m = re.match(r"^/api/jobs/linkedin/(\d+)$", path)
    if m:
        job_id = m.group(1)
        result = fetch_detail(job_id)
        upstream = result.get("upstream_status", "error")
        if upstream == "success":
            status = 200
        elif upstream == "invalid_id":
            status = 400
        elif upstream == "rate_limited":
            status = 429
        else:
            status = 502
        return _res(status, result)

    # Search endpoint: /api/jobs/linkedin
    if path != "/api/jobs/linkedin":
        return _res(404, {"error": "Not found"})

    keywords = (qs.get("q") or qs.get("keywords") or "").strip()
    location = (qs.get("location") or qs.get("l") or "").strip()
    posted_within = qs.get("posted_within") or qs.get("freshness")
    under_10 = (qs.get("under_10") or "false").lower() in ("true", "1", "yes")
    easy_apply = (qs.get("easy_apply") or "false").lower() in ("true", "1", "yes")
    sort_mode = qs.get("sort") or "newest"
    limit = int(qs.get("limit") or "50")
    max_pages = int(qs.get("max_pages") or "20")
    start = int(qs.get("start") or "0")

    result = search_linkedin(
        keywords=keywords,
        location=location,
        posted_within=posted_within,
        under_10=under_10,
        easy_apply=easy_apply,
        sort_mode=sort_mode,
        max_jobs=limit,
        max_pages=max_pages,
        start=start,
    )

    status = result.get("search_status", "failed")
    if status == "failed":
        http_status = 502
    else:
        http_status = 200

    return _res(http_status, result)


def _res(status, payload):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(payload),
    }
