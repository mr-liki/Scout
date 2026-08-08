#!/usr/bin/env python3
"""
wellfound_tracker.py - Wellfound (formerly AngelList Talent) job tracker.

Wellfound is the startup-job board. It's protected by Cloudflare, but unlike
Glassdoor the protection is FLAKY rather than absolute: direct requests from a
home IP usually return the real page (with an embedded Next.js __NEXT_DATA__
payload containing the full Apollo state). Occasionally Cloudflare answers
with a 403 captcha wall — so we retry with backoff and, if we keep getting
blocked, degrade gracefully (return [] with last_error set).

How the parsing works:
  The search page https://wellfound.com/role/<role-slug> server-renders the
  Apollo cache inside <script id="__NEXT_DATA__">:
    apolloState.data.JobListingSearchResult:<id>   -> job (title, slug,
        compensation/salary, locationNames, remote, liveStartAt, ...)
    apolloState.data.StartupResult:<id>            -> company (name, slug)
        with highlightedJobListings refs back to the JobListingSearchResult
  We build a reverse map job_ref -> company name, then flatten.

Returns jobs in the SAME format as the LinkedIn/Indeed/Glassdoor trackers so
main.py can display them identically:
    {title, company, location, link, posted_date, salary, easy_apply,
     source: "Wellfound"}

Bonus vs other platforms:
  - Startups: early-stage companies that rarely post on LinkedIn/Indeed.
  - Salary + equity (compensation) included when the listing shows one.
  - Remote flag + accepted-remote locations.

NOTE: location is NOT applied server-side on these SEO pages — we post-filter
client-side against the job's locationNames (remote jobs are kept for any
location, since remote is location-agnostic).
"""

import json
import re
import time
from datetime import datetime
from typing import List, Dict

import requests

WELLFOUND_BASE = "https://wellfound.com"

# Home IPs usually get through Cloudflare; keep a realistic browser UA.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CACHE_FILE = ".wellfound_cache.json"
CACHE_TTL_SECONDS = 900       # 15 min for real results
EMPTY_CACHE_TTL_SECONDS = 60  # 1 min for empty results
MAX_RETRIES = 4               # Cloudflare is flaky; retry with backoff
RETRY_SLEEP = 3               # seconds between attempts


def _load_cache() -> Dict:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: Dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _slugify(text: str) -> str:
    """'Machine Learning Engineer' -> 'machine-learning-engineer'."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "developer"


def _compensation_to_salary(comp: str) -> str:
    """Strip Wellfound's equity suffix ('$120k - $140k \\u2022 0.0% - 0.1%' ->
    '$120k - $140k'). Keeps the dollar/rupee salary portion only."""
    if not comp:
        return ""
    return re.split(r"\s*•\s*", comp.strip())[0].strip()


class WellfoundJobTracker:
    """Free Wellfound job search via direct fetch + Apollo state parsing."""

    def __init__(self):
        self.last_error = None
        self._cache = _load_cache()

    def build_url(self, keywords: str, location: str = "") -> str:
        """Wellfound's SEO role page. Location is handled client-side."""
        role_slug = _slugify(keywords)
        return f"{WELLFOUND_BASE}/role/{role_slug}"

    def fetch_html(self, url: str) -> str:
        """Fetch the search page with retries (Cloudflare is flaky).

        NEVER raises: any failure is recorded in self.last_error and returns
        '' so callers degrade gracefully.
        """
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=30)
                if resp.status_code == 200 and "__NEXT_DATA__" in resp.text:
                    self.last_error = None  # cleared on success
                    return resp.text
                self.last_error = (f"Wellfound status {resp.status_code}"
                                   f" (attempt {attempt + 1})")
            except Exception as e:
                self.last_error = str(e)[:120]
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_SLEEP * (attempt + 1))
        return ""

    def parse_next_data(self, html: str) -> List[Dict]:
        """Extract jobs from the embedded __NEXT_DATA__ Apollo state.

        NEVER raises: malformed HTML degrades to [] with last_error set.
        """
        try:
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                          html, re.S)
            if not m:
                self.last_error = "Wellfound: no __NEXT_DATA__ found"
                return []
            data = json.loads(m.group(1))
            apollo = data.get("props", {}).get("pageProps", {}).get("apolloState", {})
            ad = apollo.get("data", {})
            if not ad:
                self.last_error = "Wellfound: empty Apollo state"
                return []
            return self._flatten_apollo(ad)
        except Exception as e:
            self.last_error = f"Wellfound parse error: {str(e)[:80]}"
            return []

    def _flatten_apollo(self, ad: Dict) -> List[Dict]:
        """Build job dicts from JobListingSearchResult + StartupResult maps."""
        # Reverse map: JobListingSearchResult ref -> company name
        comp_map = {}
        for k, v in ad.items():
            if k.startswith("StartupResult:") and v.get("highlightedJobListings"):
                for ref in v["highlightedJobListings"]:
                    if isinstance(ref, dict) and ref.get("__ref", "").startswith("JobListingSearchResult:"):
                        comp_map[ref["__ref"]] = v.get("name", "N/A")

        jobs = []
        seen = set()
        for k, v in ad.items():
            if not k.startswith("JobListingSearchResult:"):
                continue
            title = v.get("title", "")
            if not title or k in seen:
                continue
            seen.add(k)

            company = comp_map.get(k, "N/A")
            loc_names = v.get("locationNames") or []
            remote = bool(v.get("remote")) or (v.get("remoteConfig") or {}).get("kind") == "REMOTE"
            if loc_names:
                location = ", ".join(loc_names)
            elif remote:
                location = "Remote"
            else:
                location = ""

            job_slug = v.get("slug", "")
            company_slug = _slugify(company) if company != "N/A" else ""
            link = f"{WELLFOUND_BASE}/jobs/@{company_slug}/{job_slug}" if company_slug and job_slug else ""
            if not link and v.get("id"):
                link = f"{WELLFOUND_BASE}/jobs/{v['id']}"

            posted = ""
            ts = v.get("liveStartAt")
            if ts:
                try:
                    posted = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                except Exception:
                    posted = ""

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "link": link,
                "posted_date": posted,
                "salary": _compensation_to_salary(v.get("compensation", "")),
                "easy_apply": False,
                "remote": remote,
                "source": "Wellfound",
            })
        return jobs

    def _matches_location(self, job: Dict, location: str) -> bool:
        """Client-side location filter (server ignores location on SEO pages).

        Remote jobs pass for ANY location (remote is location-agnostic).
        Otherwise the location must appear in the job's location names.
        """
        if not location:
            return True
        if job.get("remote"):
            return True
        loc = job.get("location", "")
        if not loc:
            return False
        target = location.lower().strip()
        for name in loc.lower().split(","):
            name = name.strip()
            if name and (target in name or name in target):
                return True
        return False

    def search_jobs(self, keywords: str, location: str = "", limit: int = 10) -> List[Dict]:
        """Search Wellfound. Returns jobs in CADDY's shared format."""
        self.last_error = None
        cache_key = f"{keywords.lower()}|{location.lower()}"
        cached = self._cache.get(cache_key)
        if cached:
            ttl = CACHE_TTL_SECONDS if cached.get("jobs") else EMPTY_CACHE_TTL_SECONDS
            if time.time() - cached.get("ts", 0) < ttl:
                return cached["jobs"][:limit]

        url = self.build_url(keywords, location)
        html = self.fetch_html(url)
        if not html:
            return []

        jobs = self.parse_next_data(html)
        # Location is applied client-side (the SEO pages ignore it server-side)
        jobs = [j for j in jobs if self._matches_location(j, location)]

        self._cache[cache_key] = {"ts": time.time(), "jobs": jobs}
        _save_cache(self._cache)
        return jobs[:limit]


def main():
    """Quick CLI test."""
    tracker = WellfoundJobTracker()
    print("Testing Wellfound search: 'Python Developer'...")
    jobs = tracker.search_jobs("Python Developer", "", limit=5)
    if tracker.last_error:
        print("ERROR:", tracker.last_error)
    print(f"Found {len(jobs)} jobs")
    for j in jobs[:5]:
        print(f"  - {j['title']} @ {j['company']} | {j['location']} | {j['salary']} | {j['link']}")


if __name__ == "__main__":
    main()
