#!/usr/bin/env python3
"""
jobs_store.py - Shared persistent store for found jobs.

Both the background tracker (background_tracker.py) and the CADDY chatbot
(main.py / caddy_with_linkedin.py) read and write this file so jobs found
while CADDY is closed are still available when you open it again.

Data is stored in jobs_results.json:
{
  "last_updated": "ISO timestamp",
  "jobs": [ {title, company, location, link, query, found_at, ...} ]
}
"""

import json
import os
import hashlib
from datetime import datetime

JOBS_FILE = "jobs_results.json"
MAX_JOBS = 500  # Keep the newest N jobs


def job_key(job):
    """Unique key for a job (prefer the LinkedIn job link/id)."""
    link = job.get("link") or job.get("url") or ""
    if link:
        return hashlib.md5(link.encode("utf-8")).hexdigest()
    unique = f"{job.get('title', '')}_{job.get('company', '')}_{job.get('location', '')}"
    return hashlib.md5(unique.encode("utf-8")).hexdigest()


def load_jobs():
    """Return the list of stored jobs (newest appended last)."""
    if not os.path.exists(JOBS_FILE):
        return []
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("jobs", []) or []
    except Exception:
        return []


def save_jobs(jobs):
    """Persist the job list to disk."""
    try:
        data = {
            "last_updated": datetime.now().isoformat(),
            "job_count": len(jobs),
            "jobs": jobs[-MAX_JOBS:],
        }
        with open(JOBS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[JOBS_STORE] Could not save: {e}")
        return False


def store_new_jobs(new_jobs):
    """
    Append jobs that aren't already stored. Returns the number newly added.
    Also stamps each job with a `stored_at` timestamp.
    """
    if not new_jobs:
        return 0
    existing = load_jobs()
    seen = {job_key(j) for j in existing}
    added = 0
    now = datetime.now().isoformat()
    for job in new_jobs:
        if job_key(job) not in seen:
            job["stored_at"] = now
            existing.append(job)
            seen.add(job_key(job))
            added += 1
    if added:
        save_jobs(existing)
    return added


def get_summary():
    """Small dict describing what's stored, for startup messages."""
    jobs = load_jobs()
    return {
        "count": len(jobs),
        "last_updated": jobs[-1].get("stored_at") if jobs else None,
        "queries": sorted({j.get("query", "") for j in jobs if j.get("query")}),
    }
