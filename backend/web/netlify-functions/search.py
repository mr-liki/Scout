"""
Netlify Python function: /api/search (deployed via netlify.toml)

Uses the Netlify function signature (event/context -> dict). Same engine.
"""

import json
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trackers.engine import search  # noqa: E402


def handler(event, context):
    path = event.get("path", "/")
    qs = event.get("queryStringParameters") or {}
    if path.endswith("/health"):
        return _res(200, {"status": "ok", "service": "SCOUT Jobs"})

    keywords = (qs.get("q") or qs.get("keywords") or "").strip()
    location = (qs.get("location") or qs.get("l") or "").strip()
    if not keywords:
        return _res(400, {"error": "Missing keywords (use ?q=)"})

    result = search(keywords, location, budget_seconds=18)
    return _res(200, result)


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
