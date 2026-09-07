#!/usr/bin/env python3
"""
indeed_tracker.py - Indeed job tracker for SCOUT (no API key required).

Uses Indeed's public mobile GraphQL endpoint (apis.indeed.com/graphql) with the
same request format as popular open-source scrapers (JobSpy). This works
without any API key or account.

Returns jobs in the SAME format as the LinkedIn trackers so main.py can
display them identically:
    {title, company, location, link, posted_date, source: "Indeed"}

NOTE: This Indeed API is scoped to the US job index by default. Searches for
locations outside the US (e.g. Bengaluru) may return fewer/zero results —
LinkedIn remains the better choice for non-US locations.
"""

import requests
import re
from datetime import datetime, timezone
from typing import List, Dict

# Headers reverse-engineered from Indeed's mobile app (same as JobSpy)
API_HEADERS = {
    "Host": "apis.indeed.com",
    "content-type": "application/json",
    "indeed-api-key": "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8",
    "accept": "application/json",
    "indeed-locale": "en-US",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"),
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

API_URL = "https://apis.indeed.com/graphql"

JOB_SEARCH_QUERY_TEMPLATE = """
query GetJobData {{
  jobSearch(
    what: "{what}"
    {location}
    limit: {limit}
    sort: RELEVANCE
  ) {{
    results {{
      trackingKey
      job {{
        key
        title
        dateOnIndeed
        location {{ formatted {{ short }} }}
        source {{ name }}
      }}
    }}
  }}
}}
"""


class IndeedJobTracker:
    """Free Indeed job search via the mobile GraphQL endpoint."""

    def __init__(self):
        self.last_error = None

    def build_query(self, keywords: str, location: str = "", limit: int = 25) -> str:
        """Build the GraphQL query string."""
        loc_block = ""
        if location:
            safe_loc = location.replace('"', "'")
            loc_block = f'location: {{where: "{safe_loc}", radius: 25, radiusUnit: MILES}}'
        return JOB_SEARCH_QUERY_TEMPLATE.format(
            what=keywords.replace('"', "'"),
            location=loc_block,
            limit=int(limit),
        )

    def parse_result(self, result: Dict) -> Dict:
        """Convert one GraphQL result into the shared SCOUT job format."""
        job = result.get("job", {})
        link = f"https://www.indeed.com/viewjob?jk={job.get('key', '')}"
        # dateOnIndeed is epoch milliseconds
        posted = ""
        try:
            ts = job.get("dateOnIndeed")
            if ts:
                posted = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pass
        return {
            "title": job.get("title", "N/A"),
            "company": job.get("source", {}).get("name", "N/A"),
            "location": (job.get("location", {}) or {}).get("formatted", {}).get("short", ""),
            "link": link,
            "posted_date": posted,
            "source": "Indeed",
        }

    def search_jobs(self, keywords: str, location: str = "", limit: int = 25) -> List[Dict]:
        """Search Indeed. Returns a list of jobs in SCOUT's shared format."""
        self.last_error = None
        query = self.build_query(keywords, location, limit)
        try:
            resp = requests.post(API_URL, headers=API_HEADERS, json={"query": query}, timeout=20)
            if resp.status_code != 200:
                self.last_error = f"Indeed API status {resp.status_code}"
                return []
            data = resp.json()
            if "errors" in data:
                self.last_error = str(data["errors"][0].get("message", ""))[:120]
                return []
            results = data.get("data", {}).get("jobSearch", {}).get("results", [])
            return [self.parse_result(r) for r in results]
        except Exception as e:
            self.last_error = str(e)[:120]
            return []


def main():
    """Quick CLI test."""
    tracker = IndeedJobTracker()
    print("Testing Indeed search: 'Python Developer' in 'Remote'...")
    jobs = tracker.search_jobs("Python Developer", "Remote", limit=5)
    if tracker.last_error:
        print("ERROR:", tracker.last_error)
    print(f"Found {len(jobs)} jobs")
    for j in jobs[:5]:
        print(f"  - {j['title']} @ {j['company']} | {j['location']} | {j['link']}")


if __name__ == "__main__":
    main()
