#!/usr/bin/env python3
"""
server.py - Run the ENTIRE SCOUT Jobs site locally with one command.

    python server.py            # http://localhost:8000

Serves the static frontend AND the JSON API (/api/search, /api/health,
/api/jobs/linkedin, /api/jobs/linkedin/{job_id}) from one process, using
only the Python standard library.
"""

import json
import mimetypes
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trackers.engine import search, health  # noqa: E402

ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend")
)
PORT = int(os.environ.get("PORT", 8000))
SEARCH_BUDGET = int(os.environ.get("SEARCH_BUDGET_SECONDS", 20))

INDEX_CACHE = None


def _read_index():
    global INDEX_CACHE
    if INDEX_CACHE is None:
        with open(os.path.join(ROOT, "index.html"), "rb") as f:
            INDEX_CACHE = f.read()
    return INDEX_CACHE


def _send_cors(handler):
    """Emit CORS headers on the RESPONSE."""
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        _send_cors(self)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/search":
            self._api_search(parsed.query)
            return
        if path == "/api/health":
            self._json_response(200, health())
            return

        # LinkedIn search endpoint: /api/jobs/linkedin
        if path == "/api/jobs/linkedin":
            self._api_linkedin_search(parsed.query)
            return

        # LinkedIn detail endpoint: /api/jobs/linkedin/{job_id}
        m = re.match(r"^/api/jobs/linkedin/(\d+)$", path)
        if m:
            self._api_linkedin_detail(m.group(1))
            return

        self._static(path)

    # --- API routes -------------------------------------------------------
    def _api_search(self, query_string):
        params = parse_qs(query_string)
        keywords = (params.get("q") or params.get("keywords") or [""])[0].strip()
        location = (params.get("location") or params.get("l") or [""])[0].strip()
        if not keywords:
            self._json_response(400, {"error": "Missing keywords (use ?q=)"})
            return
        result = search(keywords, location, budget_seconds=SEARCH_BUDGET)
        self._json_response(200, result)

    def _api_linkedin_search(self, query_string):
        """LinkedIn-specific search with freshness/under_10/easy_apply."""
        from trackers.linkedin_connector_tracker import search_linkedin

        params = parse_qs(query_string)
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

        # Map status to HTTP code
        status = result.get("search_status", "failed")
        if status == "failed":
            http_status = 502
        elif status == "partial":
            http_status = 200  # Partial results are still valid
        else:
            http_status = 200

        self._json_response(http_status, result)

    def _api_linkedin_detail(self, job_id):
        """Lazy detail fetch for a single LinkedIn job."""
        from trackers.linkedin_connector_tracker import fetch_detail

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

        self._json_response(http_status, result)

    def _json_response(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        _send_cors(self)
        self.end_headers()
        self.wfile.write(body)

    # --- Static files -----------------------------------------------------
    def _static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        full = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if full != ROOT and not full.startswith(ROOT + os.sep):
            self.send_error(403)
            return
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if os.path.isfile(full):
            ctype, _ = mimetypes.guess_type(full)
            with open(full, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = _read_index()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main():
    print("=" * 60)
    print("  SCOUT JOBS - All-in-one job search")
    print(f"  -> http://localhost:{PORT}")
    print(f"  -> API: http://localhost:{PORT}/api/search?q=Python Developer")
    print(f"  -> LinkedIn: http://localhost:{PORT}/api/jobs/linkedin?q=Software+Engineer")
    print("=" * 60)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGoodbye.")


if __name__ == "__main__":
    main()
