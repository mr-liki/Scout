#!/usr/bin/env python3
"""
background_tracker.py - Headless LinkedIn job tracker for CADDY.

Runs WITHOUT the chatbot, so job tracking continues even while you're not
using CADDY. Schedule it with cron / launchd (see setup_background_tracker.sh)
or run it manually:

    python background_tracker.py                  # check once, then exit
    python background_tracker.py --interval 1800  # check, wait 30 min, repeat
    python background_tracker.py --once --notify  # check once + macOS notification

How it works:
  - Reads your saved search queries from jobs_cache.json and jobs_cache_rss.json
    (whatever you added inside CADDY with "add job search" or "list X jobs").
  - Uses the FREE LinkedIn public search (no API key needed).
  - Newly found jobs are stored in jobs_results.json, which CADDY reads when
    you type "latest jobs".
  - Logs each run to background_tracker.log.

Works best when scheduled. Example cron line (every 30 minutes):
    */30 * * * * cd /path/to/Caddy && ./venv/bin/python background_tracker.py --once --notify >> background_tracker.log 2>&1
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime

from linkedin_rss_tracker import LinkedInRSSTracker
from indeed_tracker import IndeedJobTracker
from glassdoor_tracker import GlassdoorJobTracker
from wellfound_tracker import WellfoundJobTracker
import jobs_store

# Marker used to find/remove our cron entry (single source of truth — the
# shell script delegates to this module so the tag can never drift).
CRON_TAG = "caddy-background-tracker"


def log(message):
    """Print to stdout (captured by cron logs) AND append to the log file."""
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    try:
        with open("background_tracker.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_saved_queries():
    """Merge search queries from both cache files the chatbot may have written."""
    queries = []
    seen = set()
    for path in ("jobs_cache.json", "jobs_cache_rss.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for q in data.get("search_queries", []):
                keywords = (q.get("keywords") or "").strip()
                location = (q.get("location") or "").strip()
                if not keywords or "<" in keywords or ">" in keywords:
                    continue  # skip template placeholders
                key = (keywords.lower(), location.lower())
                if key in seen:
                    continue
                seen.add(key)
                queries.append({"keywords": keywords, "location": location})
        except FileNotFoundError:
            pass
        except Exception as e:
            log(f"Warning: could not read {path}: {e}")
    return queries


def check_once(notify=False):
    """Run one full check across all saved queries. Returns # of new jobs."""
    queries = load_saved_queries()
    if not queries:
        log("No saved job searches found. Add one inside CADDY first, e.g. 'add job search: Python Developer, Remote'")
        return 0

    tracker = LinkedInRSSTracker()
    # Dedup by (keywords, location) — add_search_query's own dedup compares full
    # dicts including the added_at timestamp, so it would append duplicates.
    existing = {(q.get("keywords", "").lower(), q.get("location", "").lower())
                for q in tracker.search_queries}
    for q in queries:
        key = (q["keywords"].lower(), q["location"].lower())
        if key in existing:
            continue
        tracker.add_search_query(q["keywords"], q["location"])
        existing.add(key)

    log(f"Checking {len(queries)} search(es): " +
        ", ".join(f"{q['keywords']} ({q['location'] or 'any'})" for q in queries))

    new_jobs = tracker.check_for_new_jobs()

    # Also check Indeed + Glassdoor + Wellfound (free, no keys) for each query
    indeed = IndeedJobTracker()
    glassdoor = GlassdoorJobTracker()
    wellfound = WellfoundJobTracker()
    seen_keys = {jobs_store.job_key(j) for j in new_jobs}
    for q in queries:
        for job in indeed.search_jobs(q["keywords"], q["location"], limit=10):
            key = jobs_store.job_key(job)
            if key not in seen_keys:
                seen_keys.add(key)
                new_jobs.append(job)
        for job in glassdoor.search_jobs(q["keywords"], q["location"], limit=10):
            key = jobs_store.job_key(job)
            if key not in seen_keys:
                seen_keys.add(key)
                new_jobs.append(job)
        for job in wellfound.search_jobs(q["keywords"], q["location"], limit=10):
            key = jobs_store.job_key(job)
            if key not in seen_keys:
                seen_keys.add(key)
                new_jobs.append(job)

    added = jobs_store.store_new_jobs(new_jobs)
    summary = jobs_store.get_summary()

    if added:
        log(f"FOUND {added} new job(s)! Total stored: {summary['count']}")
        for job in new_jobs[:10]:
            log(f"  - {job.get('title')} @ {job.get('company')} | {job.get('location')} | {job.get('link')}")
        if notify and sys.platform == "darwin":
            _notify_macos(added)
    else:
        log(f"No new jobs. Total stored: {summary['count']}")
    return added


def _notify_macos(count):
    """Fire a macOS notification banner (best-effort)."""
    try:
        script = f'display notification "Found {count} new job(s)" with title "CADDY Job Tracker"'
        os.system(f'osascript -e \'{script}\'')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cron management (used by main.py so everything is controlled from one file)
# ---------------------------------------------------------------------------

def get_cron_lines():
    """Return the user's current crontab as a list of lines (empty if none)."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        return [l for l in result.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def is_tracker_installed():
    """True if the background tracker cron job is currently installed."""
    return any(CRON_TAG in line for line in get_cron_lines())


def build_cron_line(interval_min=30):
    """Build the crontab line that runs the tracker every N minutes."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    python = sys.executable or "python3"
    # shlex.quote keeps the line safe if the project path contains spaces
    return (f"*/{interval_min} * * * * cd {shlex.quote(project_dir)} && {shlex.quote(python)} "
            f"{shlex.quote(os.path.abspath(__file__))} --once --notify >/dev/null 2>&1 # {CRON_TAG}")


def install_cron_tracker(interval_min=30):
    """Install (or update) the cron job. Returns True on success."""
    lines = [l for l in get_cron_lines() if CRON_TAG not in l]
    lines.append(build_cron_line(interval_min))
    try:
        proc = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                              capture_output=True, text=True, timeout=10)
        return proc.returncode == 0
    except Exception as e:
        log(f"Could not install cron: {e}")
        return False


def remove_cron_tracker():
    """Remove the background tracker cron job. Returns True on success."""
    lines = [l for l in get_cron_lines() if CRON_TAG not in l]
    try:
        proc = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                              capture_output=True, text=True, timeout=10)
        return proc.returncode == 0
    except Exception as e:
        log(f"Could not remove cron: {e}")
        return False


def get_installed_interval():
    """Return the interval (minutes) of the installed cron job, or None."""
    for line in get_cron_lines():
        if CRON_TAG in line:
            parts = line.split()
            if len(parts) > 1 and parts[0].startswith("*/"):
                try:
                    return int(parts[0][2:])
                except ValueError:
                    return None
    return None


def get_log_tail(n=5):
    """Return the last n lines of the tracker log (for status display)."""
    if not os.path.exists("background_tracker.log"):
        return []
    try:
        with open("background_tracker.log", "r", encoding="utf-8") as f:
            return f.read().splitlines()[-n:]
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(description="Headless CADDY LinkedIn job tracker")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit (good for cron)")
    parser.add_argument("--interval", type=int, default=0,
                        help="Loop forever, checking every N seconds (e.g. 1800 = 30 min)")
    parser.add_argument("--notify", action="store_true",
                        help="Show a macOS notification when new jobs are found")
    args = parser.parse_args()

    try:
        if args.interval > 0:
            log(f"Background tracker started. Checking every {args.interval}s. Ctrl+C to stop.")
            while True:
                check_once(notify=args.notify)
                time.sleep(args.interval)
        else:
            check_once(notify=args.notify)
    except KeyboardInterrupt:
        log("Stopped by user.")
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
