"""
Glassdoor proxy — routes search requests through curl_cffi's Chrome TLS
impersonation instead of a plain HTTP client.

Why this exists: Glassdoor's block is specifically a TLS/JA3 fingerprint
check (see ../GLASSDOOR_SETUP.md) — an identical request with identical
headers succeeds from plain `curl` and fails from Python's requests/urllib3,
purely because of TLS handshake differences. It's not about IP reputation
(confirmed: Deno Deploy's IP, genuinely different from Cloudflare's, still
got blocked — because Deno's fetch() doesn't impersonate Chrome's TLS
signature either). curl_cffi wraps libcurl compiled with curl-impersonate
patches, reproducing a real Chrome TLS/HTTP2 fingerprint. This is the one
thing that's ever actually worked for Glassdoor in this project (it's what
backend/glassdoor_connector.py already does).

Deploy target: Render.com free tier (or any host that can run a real Python
process with compiled deps — Cloudflare Workers and Deno Deploy can't,
since curl_cffi isn't pure JS/TS).
"""

import os
import secrets

from curl_cffi import requests as curl_requests
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

PROXY_KEY = os.environ.get("PROXY_KEY") or secrets.token_hex(24)
if not os.environ.get("PROXY_KEY"):
    print(f"[proxy] No PROXY_KEY set — generated one for this run: {PROXY_KEY}")

SEARCH_URL = "https://www.glassdoor.com/Job/jobs.htm"
AUTOCOMPLETE_URL = "https://www.glassdoor.com/autocomplete/location"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


@app.get("/health")
def health():
    return jsonify(ok=True)


def resolve_location(session, location):
    """Glassdoor's own sc.location/locKeyword text param is cosmetic — the
    server resolves the *effective* search location from the requester's
    GeoIP and silently ignores free text unless a real locId (from this
    autocomplete endpoint) is supplied too. See ../GLASSDOOR_SETUP.md.

    The frontend sends full "City, State, Country" strings (e.g.
    "Bengaluru, Karnataka, India"), but Glassdoor's autocomplete matches
    poorly against that whole string and often returns nothing — which
    made this silently fall through to GeoIP-based defaults (the proxy's
    own IP location) instead of erroring. Using just the city name (before
    the first comma) matches Glassdoor's autocomplete far more reliably."""
    term = location.split(",")[0].strip() if location else location
    if not term:
        return None
    try:
        resp = session.get(
            AUTOCOMPLETE_URL,
            params={"locationTypeFilters": "CITY,STATE,COUNTRY", "caller": "jobs", "term": term},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        results = resp.json()
        if not results:
            return None
        top = results[0]
        return {"locId": top.get("locationId"), "locT": top.get("locationType")}
    except Exception:
        return None


@app.get("/glassdoor")
def glassdoor():
    if request.headers.get("x-proxy-key") != PROXY_KEY:
        return jsonify(error="unauthorized"), 401

    query = request.args.get("query", "")
    location = request.args.get("location", "")

    try:
        session = curl_requests.Session(impersonate="chrome")

        params = {"sc.keyword": query, "p": "1"}
        if location:
            loc = resolve_location(session, location)
            if loc and loc.get("locId"):
                params["locT"] = loc["locT"]
                params["locId"] = loc["locId"]
                params["locKeyword"] = location

        resp = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return jsonify(error=f"Glassdoor HTTP {resp.status_code}: {resp.text[:300]}"), 502
        return Response(resp.text, mimetype="text/html")
    except Exception as e:
        return jsonify(error=str(e)), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
