"""
engine.py - The SCOUT Jobs search engine.

Runs all four platform trackers CONCURRENTLY under a hard time budget, then
merges + dedupes results into one unified response for the web app.

Why concurrency + a budget matters: serverless functions (Vercel / Netlify)
kill long-running requests. Each tracker has its own network timeouts, so we
give the whole search a wall-clock deadline and let slow platforms contribute
0 jobs gracefully rather than failing the request.

Each platform's search_jobs(keywords, location, limit) returns jobs in the
shared SCOUT format:
    {title, company, location, link, posted_date, source, ...}
"""

import concurrent.futures
import hashlib
import json
import time
from datetime import datetime
from typing import Dict, List

from trackers.linkedin_rss_tracker import LinkedInRSSTracker
from trackers.indeed_tracker import IndeedJobTracker
from trackers.glassdoor_tracker import GlassdoorJobTracker
from trackers.wellfound_tracker import WellfoundJobTracker

# Which platforms to query, in display order
PLATFORMS = {
    "LinkedIn": lambda: LinkedInRSSTracker(),
    "Indeed": lambda: IndeedJobTracker(),
    "Glassdoor": lambda: GlassdoorJobTracker(),
    "Wellfound": lambda: WellfoundJobTracker(),
}

DEFAULT_BUDGET_SECONDS = 18   # whole search must finish within this
DEFAULT_LIMIT_PER_PLATFORM = 10

# Tiny in-memory cache so repeat searches within minutes are instant
# (a real production system would use Redis / Vercel KV, but this keeps the
# free-tier deployment dependency-free).
_cache: Dict[str, Dict] = {}
CACHE_TTL = 120  # seconds


def job_id(job: Dict) -> str:
    """Stable unique id for a job (from its link, else title+company+location)."""
    link = job.get("link") or job.get("url") or ""
    if link:
        return hashlib.md5(link.encode("utf-8")).hexdigest()[:16]
    raw = f"{job.get('title','')}|{job.get('company','')}|{job.get('location','')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _run_platform(name: str, factory, keywords: str, location: str,
                  limit: int) -> List[Dict]:
    """Run one tracker. NEVER raises — the web app must stay up."""
    try:
        tracker = factory()
        jobs = tracker.search_jobs(keywords, location, limit=limit)
        for j in jobs or []:
            j["id"] = job_id(j)
            j["source"] = name
            j.setdefault("salary", "")
            j.setdefault("posted_date", "")
            j.setdefault("easy_apply", False)
            j.setdefault("early_applicant", False)
        return jobs or []
    except Exception as e:
        return []


def search(keywords: str, location: str = "",
           budget_seconds: int = DEFAULT_BUDGET_SECONDS,
           limit_per_platform: int = DEFAULT_LIMIT_PER_PLATFORM) -> Dict:
    """Search all platforms concurrently. Returns a JSON-serializable dict."""
    if not keywords:
        return {"error": "Missing keywords", "jobs": [], "total": 0,
                "platforms": {}, "errors": []}

    cache_key = f"{keywords.lower().strip()}|{location.lower().strip()}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached["ts"] < CACHE_TTL:
        return cached["data"]

    results: Dict[str, List[Dict]] = {}
    platform_errors: List[str] = []

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(PLATFORMS))
    try:
        futures = {
            executor.submit(_run_platform, name, factory, keywords, location,
                            limit_per_platform): name
            for name, factory in PLATFORMS.items()
        }
        # wait() NEVER raises — it returns once the budget elapses, so a slow
        # platform (Glassdoor/jina, Wellfound retries) can't crash the request
        # or block it past the wall-clock budget.
        done, not_done = concurrent.futures.wait(futures, timeout=budget_seconds)
        for fut in done:
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception:
                platform_errors.append(f"{name}: error")
        # Anything still running past the deadline gets dropped
        for fut in not_done:
            fut.cancel()
            name = futures[fut]
            platform_errors.append(f"{name}: timed out")
    finally:
        # Don't block the response on straggler threads — they carry their own
        # network timeouts and _run_platform never raises, so they die quietly.
        executor.shutdown(wait=False)

    # Merge + dedupe across platforms (same job on two boards = one result)
    merged: List[Dict] = []
    seen = set()
    for name in PLATFORMS:
        for job in results.get(name, []):
            jid = job.get("id") or job_id(job)
            if jid in seen:
                continue
            seen.add(jid)
            merged.append(job)

    payload = {
        "query": {"keywords": keywords, "location": location},
        "total": len(merged),
        "platforms": {n: len(results.get(n, [])) for n in PLATFORMS},
        "jobs": merged,
        "errors": platform_errors,
        "searched_at": datetime.utcnow().isoformat() + "Z",
    }

    _cache[cache_key] = {"ts": time.time(), "data": payload}
    return payload


def health() -> Dict:
    """Liveness + platform status for the /api/health endpoint."""
    return {
        "status": "ok",
        "service": "SCOUT Jobs",
        "platforms": list(PLATFORMS.keys()),
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Python Developer"
    loc = sys.argv[2] if len(sys.argv) > 2 else ""
    t0 = time.time()
    r = search(q, loc, budget_seconds=25)
    print(f"'{q}' in '{loc}' -> {r['total']} jobs in {round(time.time()-t0,1)}s")
    print("per platform:", r["platforms"])
    for j in r["jobs"][:6]:
        print(f"  - [{j['source']}] {j.get('title')} @ {j.get('company')} | {j.get('location')} | {j.get('salary')}")
    print("errors:", r["errors"])
