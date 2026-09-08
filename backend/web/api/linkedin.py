"""
Vercel Python serverless function: /api/jobs/linkedin

Handles LinkedIn-specific search requests with freshness, under_10,
easy_apply, and resume parameters.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import linkedin_connector as lc
from trackers.linkedin_connector_tracker import (
    search_linkedin,
    fetch_detail,
    normalize_search_response,
)


class handler:
    """Vercel serverless function handler."""

    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        from http.server import BaseHTTPRequestHandler
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # Route: /api/jobs/linkedin/{job_id} (detail)
        import re
        m = re.match(r"^/api/jobs/linkedin/(\d+)$", path)
        if m:
            job_id = m.group(1)
            result = fetch_detail(job_id)
            upstream = result.get("upstream_status", "error")
            if upstream == "success":
                http_status = 200
            elif upstream == "invalid_id":
                http_status = 400
            elif upstream == "rate_limited":
                http_status = 429
            else:
                http_status = 502
            self._json(http_status, result)
            return

        # Route: /api/jobs/linkedin (search)
        if path != "/api/jobs/linkedin":
            self._json(404, {"error": "Not found"})
            return

        keywords = (params.get("q") or params.get("keywords") or [""])[0].strip()
        location = (params.get("location") or params.get("l") or [""])[0].strip()
        posted_within = (params.get("posted_within") or params.get("freshness") or [None])[0]
        under_10 = (params.get("under_10") or ["false"])[0].lower() in ("true", "1", "yes")
        easy_apply = (params.get("easy_apply") or ["false"])[0].lower() in ("true", "1", "yes")
        sort_mode = (params.get("sort") or ["newest"])[0]
        limit = int((params.get("limit") or ["50"])[0])
        max_pages = int((params.get("max_pages") or ["20"])[0])
        start = int((params.get("start") or ["0"])[0])

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

        self._json(http_status, result)

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
