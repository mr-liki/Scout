"""
Vercel Python serverless function: /api/search

Deployed by vercel.json (runtime: python3.9). Same engine as server.py.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trackers.engine import search  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json(200, {"status": "ok", "service": "CADDY Jobs"})
            return
        params = parse_qs(parsed.query)
        keywords = (params.get("q") or params.get("keywords") or [""])[0].strip()
        location = (params.get("location") or params.get("l") or [""])[0].strip()
        if not keywords:
            self._json(400, {"error": "Missing keywords (use ?q=)"})
            return
        result = search(keywords, location, budget_seconds=18)
        self._json(200, result)

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
