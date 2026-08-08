#!/usr/bin/env python3
"""
glassdoor_tracker.py - Glassdoor job tracker for CADDY (no API key required).

Glassdoor is protected by an aggressive bot-wall (Cloudflare/PerimeterX) that
blocks direct requests with 403. CADDY bypasses it using the free r.jina.ai
reader proxy: jina fetches the page with a real browser and returns the raw
HTML (X-Return-Format: html). We then parse the job cards with BeautifulSoup.

Returns jobs in the SAME format as the LinkedIn/Indeed trackers so main.py can
display them identically:
    {title, company, location, link, posted_date, salary, easy_apply,
     source: "Glassdoor"}

Bonus vs other platforms:
  - Glassdoor returns results for international locations too (e.g. Bengaluru),
    unlike the Indeed method which is US-scoped.
  - Each result includes a salary estimate and an "Easy Apply" flag when
    Glassdoor shows one.

NOTE: r.jina.ai has free-tier rate limits (roughly 20 requests/min). A TTL
cache (15 min) avoids hammering it when the same query is searched repeatedly.
"""

import json
import re
import time
from datetime import datetime, timedelta
from urllib.parse import quote
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

# r.jina.ai reader proxy — fetches Glassdoor's real HTML through a browser,
# bypassing the Cloudflare/PerimeterX bot-wall that 403s direct requests.
# Country-aware: www.glassdoor.com is US-scoped (ignores unknown locations),
# while www.glassdoor.co.in serves Indian jobs — so Indian locations are
# routed to the .co.in domain.
JINA_BASE_COM = "https://r.jina.ai/https://www.glassdoor.com/Job/jobs.htm"
JINA_BASE_CO_IN = "https://r.jina.ai/https://www.glassdoor.co.in/Job/jobs.htm"

# Locations that should search Glassdoor India (www.glassdoor.co.in)
INDIA_LOCATIONS = {
    "bengaluru", "bangalore", "mumbai", "delhi", "new delhi", "noida", "gurgaon",
    "gurugram", "hyderabad", "pune", "chennai", "kolkata", "india", "ahmedabad",
    "kochi", "indore", "chandigarh", "jaipur", "kerala", "tamil nadu",
}
# NOTE: do NOT send a custom User-Agent — jina's reader rejects non-default
# UAs with 403 (anti-abuse). requests' default UA works.
JINA_HEADERS = {
    "Accept": "text/plain",
    "X-Return-Format": "html",
}

CACHE_FILE = ".glassdoor_cache.json"
CACHE_TTL_SECONDS = 900       # 15 min for real results
EMPTY_CACHE_TTL_SECONDS = 60  # 1 min for empty results (avoids hammering jina
                              # on flaky queries while still allowing fast retries)


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


def _age_to_date(age_text: str) -> str:
    """Convert Glassdoor's age label ('2d', '30d+', '1h') to a YYYY-MM-DD date."""
    age_text = (age_text or "").strip().lower().replace("+", "")
    m = re.match(r"(\d+)\s*([hdwmy])", age_text)
    if not m:
        return ""
    num = int(m.group(1))
    unit = m.group(2)
    days = {"h": 0, "d": num, "w": num * 7, "m": num * 30, "y": num * 365}.get(unit, 0)
    try:
        return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _company_from_slug(href: str, title: str = "") -> str:
    """Fallback: parse company from URL slug like 'ai-automation-engineer-go-west-it-JV_...'.

    The slug is '<title-slug>-<company-slug>-JV_...'. We strip the known
    title-slug prefix and take whatever remains. Returns 'N/A' when the
    company can't be recovered cleanly (a wrong guess is worse than none).
    """
    try:
        slug = href.split("/")[-1]
        slug = re.split(r"-JV_[A-Z0-9_,]+\.htm", slug)[0]
        title_slug = re.sub(r"[^a-z0-9]+|&", "-", title.lower()).strip("-")
        company_slug = slug
        if title_slug and slug.startswith(title_slug):
            company_slug = slug[len(title_slug):].strip("-")
        if not company_slug or "-" not in company_slug:
            return "N/A"
        return " ".join(w.capitalize() for w in company_slug.split("-"))
    except Exception:
        return "N/A"


class GlassdoorJobTracker:
    """Free Glassdoor job search via the r.jina.ai reader proxy + HTML parsing."""

    def __init__(self):
        self.last_error = None
        self._cache = _load_cache()

    def build_url(self, keywords: str, location: str = "") -> str:
        """Build the Glassdoor search URL (passed through the jina proxy).

        Indian locations use www.glassdoor.co.in so results are Indian jobs
        rather than Glassdoor's US index.
        """
        base = JINA_BASE_COM
        loc = location.lower().strip()
        if loc and any(re.search(r"\b" + re.escape(tok) + r"\b", loc) for tok in INDIA_LOCATIONS):
            base = JINA_BASE_CO_IN
        if not location:
            location = "United States"
        qs = f"sc.keyword={quote(keywords)}&sc.location={quote(location)}"
        return f"{base}?{qs}"

    @staticmethod
    def _looks_like_challenge(html: str) -> bool:
        """True if the page is Glassdoor's bot-wall rather than a real results
        page — jina sometimes renders the wall. Uses the precise title match
        plus challenge-specific markers, NOT the bare word 'security' (which
        legitimately appears in meta descriptions of 'security engineer'
        searches and would cause false positives)."""
        lowered = html.lower()
        if "<title>security | glassdoor" in lowered:
            return True
        markers = ["access denied", "cf-chl-", "attention required",
                   "just a moment", "checking your browser", "verify you are human"]
        has_job_markers = ("job-card-wrapper" in html
                           or 'data-test="joblisting"' in html or "jl=" in html)
        return any(m in lowered for m in markers) and not has_job_markers

    def fetch_html(self, url: str, no_cache: bool = False) -> str:
        """Fetch Glassdoor's raw HTML via the jina proxy.

        NEVER raises: any network error / timeout / non-200 is recorded in
        self.last_error and returns "" so callers degrade gracefully.
        """
        headers = dict(JINA_HEADERS)
        if no_cache:
            headers["X-No-Cache"] = "true"  # bypass jina's URL cache for retries
        try:
            resp = requests.get(url, headers=headers, timeout=90)
            if resp.status_code != 200:
                self.last_error = f"jina proxy status {resp.status_code}"
                return ""
            return resp.text
        except Exception as e:
            self.last_error = str(e)[:120]
            return ""

    def parse_job_cards(self, html: str, base_domain: str = "https://www.glassdoor.com") -> List[Dict]:
        """Parse job cards from Glassdoor's rendered HTML.

        NEVER raises: malformed HTML (NUL bytes, encoding issues) degrades to
        [] with self.last_error set — the integration's contract is that
        search_jobs never raises.
        """
        try:
            soup = BeautifulSoup(html, "lxml")
            return self._parse_cards_from_soup(soup, base_domain)
        except Exception as e:
            self.last_error = f"Glassdoor parse error: {str(e)[:80]}"
            return []

    def _parse_cards_from_soup(self, soup, base_domain: str) -> List[Dict]:
        """Extract job cards from a parsed BeautifulSoup document."""
        jobs = []
        seen = set()
        for card in soup.select('[data-test="jobListing"]'):
            a = card.select_one('a[data-test="job-title"]')
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not href.startswith("http"):
                href = base_domain + href
            job_id = card.get("data-jobid", "")
            link = href or (f"https://www.glassdoor.com/job-listing/j.htm?jl={job_id}" if job_id else "")
            if not link or link in seen:
                continue
            seen.add(link)

            company_el = card.select_one('[class*="compactEmployerName"]')
            company = company_el.get_text(strip=True) if company_el else _company_from_slug(href, title)

            loc_el = card.select_one('[data-test="emp-location"]')
            location = loc_el.get_text(strip=True) if loc_el else ""

            salary_el = card.select_one('[data-test="detailSalary"]')
            salary = ""
            if salary_el:
                # Strip Glassdoor's source suffixes so the display stays clean
                # (case-insensitive: the .co.in pages write "(Glassdoor Est.)")
                salary = re.sub(r"\s+", " ", salary_el.get_text(" ", strip=True))
                salary = re.sub(r"\s*\((?:Glassdoor est\.|Employer provided)\)\s*$", "", salary, flags=re.I)

            age_el = card.select_one('[data-test="job-age"]')
            age_text = age_el.get_text(strip=True) if age_el else ""
            posted = _age_to_date(age_text)

            easy_apply = bool(card.select_one('[class*="easyApplyTag"]'))

            jobs.append({
                "title": title,
                "company": company or "N/A",
                "location": location,
                "link": link,
                "posted_date": posted,
                "salary": salary,
                "easy_apply": easy_apply,
                "source": "Glassdoor",
            })
        return jobs

    def search_jobs(self, keywords: str, location: str = "", limit: int = 10) -> List[Dict]:
        """Search Glassdoor. Returns a list of jobs in CADDY's shared format."""
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

        # Glassdoor's bot-wall is flaky through jina: if we got the 'Security'
        # challenge page, retry once bypassing jina's cache. Never cache a wall.
        if self._looks_like_challenge(html):
            html = self.fetch_html(url, no_cache=True)
            if not html or self._looks_like_challenge(html):
                self.last_error = "Glassdoor bot-wall challenge (try again in a minute)"
                return []

        base_domain = "https://www.glassdoor.com"
        if ".co.in" in url:
            base_domain = "https://www.glassdoor.co.in"
        jobs = self.parse_job_cards(html, base_domain)

        # Safety net: if card parsing found nothing, fall back to the page's
        # JSON-LD ItemList (title + URL only).
        if not jobs:
            from_jsonld = re.findall(r'\"name\":\"([^\"]+)\",\"url\":\"(https://www\.glassdoor\.(?:com|co\.in)/job-listing/[^\"]+?jl=\d+)\"', html)
            jobs = [{"title": t, "company": "N/A", "location": "",
                     "link": u, "posted_date": "", "salary": "",
                     "easy_apply": False, "source": "Glassdoor"}
                    for t, u in dict(from_jsonld).items()]

        # Cache results (empty results get a short TTL so a challenge/flaky
        # page isn't suppressed for 15 min, but repeated queries don't hammer
        # jina's free tier either).
        self._cache[cache_key] = {"ts": time.time(), "jobs": jobs}
        _save_cache(self._cache)
        return jobs[:limit]


def main():
    """Quick CLI test."""
    tracker = GlassdoorJobTracker()
    print("Testing Glassdoor search: 'Python Developer' in 'United States'...")
    jobs = tracker.search_jobs("Python Developer", "", limit=5)
    if tracker.last_error:
        print("ERROR:", tracker.last_error)
    print(f"Found {len(jobs)} jobs")
    for j in jobs[:5]:
        print(f"  - {j['title']} @ {j['company']} | {j['location']} | {j['salary']} | {j['link']}")


if __name__ == "__main__":
    main()
