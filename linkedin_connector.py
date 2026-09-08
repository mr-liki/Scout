import argparse
import html
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter


# ============================================================
# SCOUTJOBS - LINKEDIN CONNECTOR
# ============================================================
#
# Verified LinkedIn filter mapping from the current job-search UI:
#
#   f_EA=true  -> EARLY_APPLICANT -> LinkedIn "Under 10 applicants"
#   f_AL=true  -> APPLY_WITH_LINKEDIN -> Easy Apply
#   sortBy=DD  -> newest first
#
# Freshness policy:
#
# LinkedIn's public guest search did not reliably enforce arbitrary
# sub-hour f_TPR values such as r600/r1800. For a requested window
# below one hour, the connector asks LinkedIn for r3600 and applies
# the user's smaller window locally.
#
# LinkedIn exposes relative display text such as "7 minutes ago",
# not an exact posting timestamp. Therefore freshness is reported as
# an approximate filter result, never as an exact 600-second proof.
# The connector records when the age was observed and accounts for
# elapsed runtime before final output.
#
# Search failures are never silently converted into successful empty
# results. The returned JSON includes search_status, search_complete,
# stop_reason, and structured errors.
#
# The connector uses LinkedIn public guest job surfaces only. It does
# not require login cookies, session tokens, or Premium credentials.
# ============================================================


SEARCH_URL = (
    "https://www.linkedin.com/"
    "jobs-guest/jobs/api/seeMoreJobPostings/search"
)

DETAIL_URL = (
    "https://www.linkedin.com/"
    "jobs-guest/jobs/api/jobPosting/{job_id}"
)

PAGE_SIZE = 10
DEFAULT_TIMEOUT = (8, 20)

# Conservative, adaptive request pacing. These defaults prioritize
# reliability over raw speed for long pagination runs.
DEFAULT_RATE_MIN_INTERVAL = 3.0
DEFAULT_RATE_MAX_INTERVAL = 15.0
DEFAULT_RATE_COOLDOWN_BASE = 15.0
DEFAULT_RATE_COOLDOWN_CAP = 90.0
DEFAULT_RATE_MAX_ATTEMPTS = 5
DEFAULT_UNEXPECTED_RESPONSE_RETRIES = 3
DEFAULT_RATE_BURST_SIZE = 4
DEFAULT_RATE_BURST_REST = 8.0

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ============================================================
# EXCEPTIONS
# ============================================================


class LinkedInError(Exception):
    pass


class LinkedInRateLimited(LinkedInError):
    pass


class LinkedInTemporaryError(LinkedInError):
    pass


class LinkedInUnexpectedResponse(LinkedInError):
    pass


# ============================================================
# ADAPTIVE RATE-LIMIT CONTROLLER
# ============================================================


class AdaptiveRateController:
    """
    Shared per-session pacing and cooldown controller.

    Goals:
      - avoid bursty request patterns
      - honor Retry-After when LinkedIn provides it
      - back off more aggressively after repeated 429/soft-block events
      - slowly recover toward the configured minimum interval
      - expose telemetry so partial searches are diagnosable

    This cannot force an upstream service to accept requests, but it makes
    the connector fail-safe: it waits, retries within a bounded policy, and
    reports remaining upstream throttling instead of hiding it.
    """

    def __init__(
        self,
        min_interval=DEFAULT_RATE_MIN_INTERVAL,
        max_interval=DEFAULT_RATE_MAX_INTERVAL,
        cooldown_base=DEFAULT_RATE_COOLDOWN_BASE,
        cooldown_cap=DEFAULT_RATE_COOLDOWN_CAP,
        burst_size=DEFAULT_RATE_BURST_SIZE,
        burst_rest=DEFAULT_RATE_BURST_REST,
    ):
        self.min_interval = max(0.0, float(min_interval))
        self.max_interval = max(
            self.min_interval,
            float(max_interval),
        )
        self.cooldown_base = max(1.0, float(cooldown_base))
        self.cooldown_cap = max(
            self.cooldown_base,
            float(cooldown_cap),
        )
        self.burst_size = max(0, int(burst_size))
        self.burst_rest = max(0.0, float(burst_rest))

        self.current_interval = self.min_interval
        self.last_request_monotonic = None
        self.cooldown_until_monotonic = 0.0

        self.total_requests = 0
        self.successful_requests = 0
        self.rate_limit_events = 0
        self.soft_limit_events = 0
        self.soft_limit_recoveries = 0
        self.network_retry_events = 0
        self.server_retry_events = 0
        self.total_sleep_seconds = 0.0
        self.consecutive_limit_events = 0
        self.success_streak = 0
        self.requests_since_break = 0
        self.proactive_breaks = 0

    def _sleep(self, seconds, reason=None):
        seconds = max(0.0, float(seconds))
        if seconds <= 0:
            return

        if reason:
            print(
                f"  Rate controller: {reason}; "
                f"waiting {seconds:.1f}s..."
            )

        self.total_sleep_seconds += seconds
        time.sleep(seconds)

    def before_request(self):
        now = time.monotonic()

        if (
            self.burst_size > 0
            and self.burst_rest > 0
            and self.requests_since_break >= self.burst_size
        ):
            self.proactive_breaks += 1
            self.requests_since_break = 0
            self._sleep(
                self.burst_rest + random.uniform(0.2, 0.8),
                reason="proactive burst break",
            )
            now = time.monotonic()

        if now < self.cooldown_until_monotonic:
            self._sleep(
                self.cooldown_until_monotonic - now,
                reason="cooldown active",
            )
            now = time.monotonic()

        if self.last_request_monotonic is not None:
            elapsed = now - self.last_request_monotonic
            remaining = self.current_interval - elapsed
            if remaining > 0:
                # Small jitter avoids fixed-interval bursts.
                remaining += random.uniform(0.05, 0.35)
                self._sleep(remaining)

        self.last_request_monotonic = time.monotonic()
        self.total_requests += 1
        self.requests_since_break += 1

    def on_success(self):
        self.successful_requests += 1
        self.success_streak += 1
        self.consecutive_limit_events = 0

        # Recover slowly. A single success does not immediately return to
        # aggressive pacing after a limit event.
        if self.success_streak >= 5:
            self.current_interval = max(
                self.min_interval,
                self.current_interval * 0.90,
            )
            self.success_streak = 0

    def _penalty_delay(self, retry_after=None, soft=False):
        self.success_streak = 0
        self.requests_since_break = 0
        self.consecutive_limit_events += 1

        if soft:
            self.soft_limit_events += 1
        else:
            self.rate_limit_events += 1

        # Increase ongoing request spacing after every limiting signal.
        self.current_interval = min(
            self.max_interval,
            max(
                self.min_interval,
                self.current_interval * 1.6,
                self.min_interval + 1.0,
            ),
        )

        exponential = self.cooldown_base * (
            2 ** max(0, self.consecutive_limit_events - 1)
        )

        # Cap our own exponential policy, but never shorten an explicit
        # Retry-After supplied by LinkedIn.
        delay = min(exponential, self.cooldown_cap)
        if retry_after is not None:
            delay = max(delay, float(retry_after))

        delay += random.uniform(0.25, 1.25)

        self.cooldown_until_monotonic = max(
            self.cooldown_until_monotonic,
            time.monotonic() + delay,
        )

        return delay

    def on_rate_limit(self, retry_after=None):
        return self._penalty_delay(
            retry_after=retry_after,
            soft=False,
        )

    def on_soft_limit(self):
        return self._penalty_delay(
            retry_after=None,
            soft=True,
        )

    def on_soft_limit_recovered(self):
        self.soft_limit_recoveries += 1

    def on_network_retry(self):
        self.network_retry_events += 1

    def on_server_retry(self):
        self.server_retry_events += 1

    def snapshot(self):
        return {
            "min_interval_seconds": round(self.min_interval, 3),
            "current_interval_seconds": round(
                self.current_interval, 3
            ),
            "max_interval_seconds": round(self.max_interval, 3),
            "cooldown_base_seconds": round(self.cooldown_base, 3),
            "cooldown_cap_seconds": round(self.cooldown_cap, 3),
            "burst_size": self.burst_size,
            "burst_rest_seconds": round(self.burst_rest, 3),
            "proactive_breaks": self.proactive_breaks,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "rate_limit_events": self.rate_limit_events,
            "soft_limit_events": self.soft_limit_events,
            "soft_limit_recoveries": self.soft_limit_recoveries,
            "network_retry_events": self.network_retry_events,
            "server_retry_events": self.server_retry_events,
            "total_sleep_seconds": round(self.total_sleep_seconds, 3),
        }


def _parse_retry_after(value):
    """Parse Retry-After as seconds or RFC/HTTP date."""
    if value is None:
        return None

    value = str(value).strip()
    if not value:
        return None

    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(
            0.0,
            dt.timestamp() - time.time(),
        )
    except (TypeError, ValueError, OverflowError):
        return None


# ============================================================
# GENERAL HELPERS
# ============================================================


def utc_iso(epoch_seconds=None):
    if epoch_seconds is None:
        epoch_seconds = time.time()

    return datetime.fromtimestamp(
        epoch_seconds,
        tz=timezone.utc,
    ).isoformat()


def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return " ".join(value.split())


def clean_multiline_text(element):
    if not element:
        return None

    raw = element.get_text("\n", strip=True)
    lines = []

    for line in raw.splitlines():
        line = clean_text(line)
        if line:
            lines.append(line)

    return "\n".join(lines)


def clean_url(url):
    if not url:
        return None

    url = html.unescape(url)
    parts = urlsplit(url)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            "",
            "",
        )
    )


def extract_job_id_from_url(url):
    if not url:
        return None

    match = re.search(
        r"-(\d+)(?:[/?#]|$)",
        url,
    )

    return match.group(1) if match else None


# ============================================================
# DURATION / SERVER WINDOW
# ============================================================


def parse_duration(value):
    """
    Supported examples:
      5m, 10m, 30m
      1h, 2h, 24h
      1d, 7d, 30d

    Returns seconds.
    """
    if value is None:
        return None

    value = str(value).strip().lower()

    match = re.fullmatch(
        r"(\d+)\s*([mhd])",
        value,
    )

    if not match:
        raise ValueError(
            "Invalid --posted-within value. "
            "Use values such as 10m, 30m, 1h, 24h, 7d."
        )

    amount = int(match.group(1))
    unit = match.group(2)

    if amount <= 0:
        raise ValueError(
            "Duration must be greater than zero."
        )

    multiplier = {
        "m": 60,
        "h": 3600,
        "d": 86400,
    }

    return amount * multiplier[unit]


def validate_start_offset(start):
    """
    Validate a manual --start resume offset.

    LinkedIn guest search pagination uses PAGE_SIZE=10, so any valid
    resume offset must land exactly on a page boundary.
    """
    if start is None:
        return 0

    try:
        start = int(start)
    except (TypeError, ValueError):
        raise ValueError(
            "--start must be an integer."
        )

    if start < 0:
        raise ValueError(
            "--start must be >= 0."
        )

    if start % PAGE_SIZE != 0:
        raise ValueError(
            "--start must be a multiple of "
            f"{PAGE_SIZE} (LinkedIn pagination page size)."
        )

    return start


def make_tpr_value(seconds):
    if seconds is None:
        return None

    return f"r{int(seconds)}"


def choose_server_window(requested_seconds):
    """
    Use a one-hour LinkedIn server window for any requested
    sub-hour freshness filter, then apply the requested cutoff
    locally.
    """
    if requested_seconds is None:
        return None

    if requested_seconds < 3600:
        return 3600

    return requested_seconds


# ============================================================
# RELATIVE POSTING AGE / FRESHNESS
# ============================================================


def parse_relative_posted_minutes(text):
    """
    Convert LinkedIn relative display text to approximate minutes.

    This is intentionally approximate because LinkedIn does not
    expose an exact posting second through this public HTML field.
    """
    if not text:
        return None

    value = clean_text(text).lower()

    if value in {
        "just now",
        "moments ago",
        "few seconds ago",
        "a few seconds ago",
        "less than a minute ago",
        "under a minute ago",
    }:
        return 0

    if re.search(
        r"\b\d+\s+seconds?\s+ago\b",
        value,
    ):
        return 0

    match = re.search(
        r"\b(\d+)\s+minutes?\s+ago\b",
        value,
    )

    if match:
        return int(match.group(1))

    match = re.search(
        r"\b(\d+)\s+hours?\s+ago\b",
        value,
    )

    if match:
        return int(match.group(1)) * 60

    match = re.search(
        r"\b(\d+)\s+days?\s+ago\b",
        value,
    )

    if match:
        return int(match.group(1)) * 1440

    match = re.search(
        r"\b(\d+)\s+weeks?\s+ago\b",
        value,
    )

    if match:
        return int(match.group(1)) * 10080

    match = re.search(
        r"\b(\d+)\s+months?\s+ago\b",
        value,
    )

    if match:
        return int(match.group(1)) * 43200

    return None


def record_posted_observation(
    job,
    posted_text,
    source,
    observed_at_epoch=None,
):
    if observed_at_epoch is None:
        observed_at_epoch = time.time()

    job["posted"] = clean_text(posted_text)
    job["posted_age_minutes"] = (
        parse_relative_posted_minutes(posted_text)
    )
    job["freshness_source"] = source
    job["freshness_observed_at"] = utc_iso(
        observed_at_epoch
    )
    job["freshness_observed_age_seconds"] = (
        int(job["posted_age_minutes"] * 60)
        if job["posted_age_minutes"] is not None
        else None
    )
    job["_freshness_observed_at_epoch"] = (
        float(observed_at_epoch)
    )
    job["_freshness_observed_monotonic"] = (
        time.monotonic()
    )

    return job


def evaluate_job_freshness(
    job,
    requested_seconds,
    now_epoch=None,
):
    """
    Re-evaluate the observed relative age at the requested check time.

    Important: the source is still a rounded/relative LinkedIn display,
    so freshness_exact is always False. elapsed runtime is added to the
    displayed age estimate so a job cannot stay artificially frozen at
    an earlier observed age throughout a long run.
    """
    if requested_seconds is None:
        job["freshness_filter_passed"] = None
        job["freshness_exact"] = False
        return None

    if now_epoch is None:
        now_epoch = time.time()

    age_minutes = job.get("posted_age_minutes")
    observed_at_epoch = job.get(
        "_freshness_observed_at_epoch"
    )
    observed_monotonic = job.get(
        "_freshness_observed_monotonic"
    )

    job["freshness_requested_seconds"] = int(
        requested_seconds
    )
    job["freshness_exact"] = False
    job["freshness_basis"] = (
        "linkedin_relative_display_plus_elapsed_time"
    )
    job["freshness_checked_at"] = utc_iso(now_epoch)

    if age_minutes is None:
        job["freshness_filter_passed"] = None
        job["freshness_age_estimate_seconds_at_check"] = None
        return None

    if observed_at_epoch is None:
        observed_at_epoch = now_epoch

    # A monotonic clock is immune to wall-clock adjustments during a long
    # run. It is only used to compute elapsed seconds internally; it is
    # never serialized into output, since a raw monotonic value has no
    # meaning outside this process.
    if observed_monotonic is not None:
        elapsed_seconds = max(
            0.0,
            time.monotonic() - float(observed_monotonic),
        )
    else:
        elapsed_seconds = max(
            0.0,
            float(now_epoch) - float(observed_at_epoch),
        )

    estimated_age_seconds = (
        float(age_minutes) * 60.0
        + elapsed_seconds
    )

    # LinkedIn's display is minute-rounded ("5 minutes ago" ~= 300s), so
    # compare on deterministic whole seconds: truncate (never round)
    # the elapsed time. For a 300s window and "5 minutes ago",
    # elapsed < 1 whole second still passes (300 + 0 <= 300) while
    # elapsed >= 1 whole second fails (300 + 1 > 300). Python's
    # banker's rounding is deliberately avoided here. freshness_exact
    # stays False: this is still an approximate relative-age cutoff.
    elapsed_whole_seconds = int(elapsed_seconds)
    estimated_whole_seconds = (
        int(float(age_minutes) * 60.0)
        + elapsed_whole_seconds
    )

    passed = (
        estimated_whole_seconds
        <= float(requested_seconds)
    )

    job["freshness_filter_passed"] = bool(passed)
    job["freshness_age_estimate_seconds_at_check"] = (
        estimated_whole_seconds
    )

    return bool(passed)


# ============================================================
# APPLICANT INFORMATION
# ============================================================


def _parse_count_token(token):
    if token is None:
        return None

    normalized = re.sub(
        r"[\s,]",
        "",
        str(token),
    )

    if not normalized.isdigit():
        return None

    return int(normalized)


def parse_applicant_information(text):
    """
    Parse applicant text without confusing CTA copy with exact counts.

    Examples:
      "7 applicants"          -> exact 7
      "1,001 applicants"      -> exact 1001
      "Over 9 applicants"     -> minimum 10
      "Over 200 applicants"   -> minimum 201
      "10+ applicants"        -> minimum 10
      "Be among the first 25 applicants" -> unknown
    """
    result = {
        "applicant_count": None,
        "applicant_count_exact": False,
        "applicant_count_minimum": None,
        "applicant_count_relation": None,
    }

    if not text:
        return result

    value = clean_text(text)
    number = r"(\d[\d,\s]*)"

    # CTA, not an applicant count.
    if re.search(
        rf"\bfirst\s+{number}\s+applicants?\b",
        value,
        re.IGNORECASE,
    ):
        return result

    # Strictly greater than N means minimum N + 1.
    match = re.search(
        rf"\b(?:over|more\s+than)\s+{number}\s+applicants?\b",
        value,
        re.IGNORECASE,
    )

    if match:
        parsed = _parse_count_token(match.group(1))
        if parsed is not None:
            result["applicant_count_minimum"] = parsed + 1
            result["applicant_count_relation"] = "greater_than"
        return result

    # N+ applicants means at least N.
    match = re.search(
        rf"\b{number}\s*\+\s*applicants?\b",
        value,
        re.IGNORECASE,
    )

    if match:
        parsed = _parse_count_token(match.group(1))
        if parsed is not None:
            result["applicant_count_minimum"] = parsed
            result["applicant_count_relation"] = "at_least"
        return result

    # Exact visible count.
    match = re.search(
        rf"\b{number}\s+applicants?\b",
        value,
        re.IGNORECASE,
    )

    if match:
        parsed = _parse_count_token(match.group(1))
        if parsed is not None:
            result["applicant_count"] = parsed
            result["applicant_count_exact"] = True
            result["applicant_count_relation"] = "exact"

    return result


# ============================================================
# HTTP
# ============================================================


def create_session(
    rate_min_interval=DEFAULT_RATE_MIN_INTERVAL,
    rate_max_interval=DEFAULT_RATE_MAX_INTERVAL,
    rate_cooldown_base=DEFAULT_RATE_COOLDOWN_BASE,
    rate_cooldown_cap=DEFAULT_RATE_COOLDOWN_CAP,
    rate_burst_size=DEFAULT_RATE_BURST_SIZE,
    rate_burst_rest=DEFAULT_RATE_BURST_REST,
):
    session = requests.Session()

    # Disable urllib3's implicit retry loop. All retry/backoff behavior is
    # explicit and observable in safe_get().
    adapter = HTTPAdapter(
        max_retries=0,
        pool_connections=10,
        pool_maxsize=10,
    )

    session.mount("https://", adapter)
    session.headers.update(DEFAULT_HEADERS)
    session.scout_rate_controller = AdaptiveRateController(
        min_interval=rate_min_interval,
        max_interval=rate_max_interval,
        cooldown_base=rate_cooldown_base,
        cooldown_cap=rate_cooldown_cap,
        burst_size=rate_burst_size,
        burst_rest=rate_burst_rest,
    )

    return session


def _rate_controller(session):
    controller = getattr(
        session,
        "scout_rate_controller",
        None,
    )

    if controller is None:
        controller = AdaptiveRateController()
        session.scout_rate_controller = controller

    return controller


def safe_get(
    session,
    url,
    params=None,
    attempts=DEFAULT_RATE_MAX_ATTEMPTS,
    timeout=DEFAULT_TIMEOUT,
    mark_success=True,
):
    """
    Bounded, adaptive GET.

    429 behavior:
      * globally slows subsequent requests
      * honors Retry-After when available
      * otherwise uses a conservative exponential cooldown
      * retries within a finite attempt budget

    The method never turns an exhausted rate-limit condition into an empty
    result. It raises LinkedInRateLimited so search status becomes partial or
    failed explicitly.
    """
    controller = _rate_controller(session)
    last_error = None

    attempts = max(1, int(attempts))

    for attempt in range(1, attempts + 1):
        controller.before_request()

        try:
            response = session.get(
                url,
                params=params,
                timeout=timeout,
            )

        except (
            requests.Timeout,
            requests.ConnectionError,
        ) as exc:
            last_error = exc
            controller.on_network_retry()

            if attempt >= attempts:
                raise LinkedInTemporaryError(str(exc))

            delay = min(
                2.0 * attempt
                + random.uniform(0.25, 1.0),
                15.0,
            )

            print(
                "  Temporary network error. "
                f"Retrying in {delay:.1f}s..."
            )
            controller._sleep(delay)
            continue

        if response.status_code == 429:
            retry_after = _parse_retry_after(
                response.headers.get("Retry-After")
            )
            delay = controller.on_rate_limit(
                retry_after=retry_after
            )

            if attempt >= attempts:
                raise LinkedInRateLimited(
                    "LinkedIn returned HTTP 429 after "
                    f"{attempts} controlled attempts."
                )

            print(
                "  LinkedIn rate limit (429). "
                f"Adaptive interval is now "
                f"{controller.current_interval:.1f}s."
            )
            # before_request() will honor the cooldown on the next attempt.
            continue

        if response.status_code in {
            500,
            502,
            503,
            504,
        }:
            controller.on_server_retry()

            if attempt >= attempts:
                raise LinkedInTemporaryError(
                    "LinkedIn returned HTTP "
                    f"{response.status_code}."
                )

            delay = min(
                (2 ** (attempt - 1))
                + random.uniform(0.25, 1.0),
                15.0,
            )

            print(
                "  LinkedIn server error "
                f"{response.status_code}. "
                f"Retrying in {delay:.1f}s..."
            )
            controller._sleep(delay)
            continue

        if response.status_code == 999:
            # Treat 999 as a hard upstream rejection, not something to hammer.
            controller.on_soft_limit()
            raise LinkedInRateLimited(
                "LinkedIn returned HTTP 999. Public guest access "
                "is currently being rejected."
            )

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LinkedInError(str(exc))

        response.encoding = "utf-8"
        if mark_success:
            controller.on_success()
        return response

    raise LinkedInTemporaryError(str(last_error))


# ============================================================
# SEARCH PARAMETER BUILDER
# ============================================================


def build_search_params(
    keywords,
    location,
    start=0,
    server_window_seconds=None,
    under_10=False,
    easy_apply=False,
    sort_mode="newest",
):
    params = {
        "keywords": keywords,
        "location": location,
        "start": start,
    }

    params["sortBy"] = (
        "DD" if sort_mode == "newest" else "R"
    )

    if server_window_seconds is not None:
        params["f_TPR"] = make_tpr_value(
            server_window_seconds
        )

    # Confirmed mapping from LinkedIn's current job-search UI.
    if under_10:
        params["f_EA"] = "true"

    if easy_apply:
        params["f_AL"] = "true"

    return params


# ============================================================
# SEARCH RESPONSE VALIDATION
# ============================================================


# Shared interstitial/block markers for HTTP 200 semantic validation.
# Used by both search- and detail-response classifiers so a
# challenge/authwall/interstitial body is never mistaken for success.
_INTERSTITIAL_MARKERS = (
    "challenge",
    "captcha",
    "verify you are human",
    "security verification",
    "unusual activity",
    "automated activity",
    "sign in",
    "signin",
    "authwall",
    "checkpoint",
    "access denied",
    "request blocked",
    "too many requests",
    "temporarily restricted",
)


def _fragment_has_visible_text(text):
    """True if an HTML fragment contains any human-visible text."""
    no_comments = re.sub(
        r"<!--.*?-->",
        "",
        text or "",
        flags=re.DOTALL,
    )
    no_tags = re.sub(
        r"<[^>]*>",
        " ",
        no_comments,
    )
    return bool(no_tags.strip())


def classify_search_response_html(
    text,
    previous_page_card_count=None,
):
    """
    Classify LinkedIn guest-search HTTP 200 bodies.

    Returns one of:
      - "cards"          : normal result fragment with job cards
      - "empty"          : legitimate empty body
      - "terminal_empty" : benign end-of-results fragment: no job cards,
                             no block/challenge markers, not a full
                             document, no human-visible text (e.g. an
                             empty markup/comment fragment), seen after
                             a short final page (< PAGE_SIZE)

    Suspicious or ambiguous full-page responses raise
    LinkedInUnexpectedResponse and enter bounded soft-limit recovery.

    A short previous page alone is NOT sufficient proof of
    end-of-results: LinkedIn has returned short (e.g. 9-card) pages in
    the middle of valid pagination. Any fragment carrying visible text
    such as "temporary backend issue" stays inconclusive and raises
    LinkedInUnexpectedResponse unless positively benign.
    """
    stripped = (text or "").strip()

    if not stripped:
        return "empty"

    if "job-search-card" in stripped:
        return "cards"

    lowered = stripped.lower()

    suspicious_markers = _INTERSTITIAL_MARKERS

    marker = next(
        (
            item
            for item in suspicious_markers
            if item in lowered
        ),
        None,
    )

    if marker:
        raise LinkedInUnexpectedResponse(
            "LinkedIn returned HTTP 200 but the response "
            f"looks like an interstitial/block page ({marker})."
        )

    # The seeMoreJobPostings endpoint normally returns an HTML fragment,
    # not a complete <html>/<head>/<body> document. A full document with
    # no cards is therefore still ambiguous even if it lacks a known
    # marker and must not be converted into a successful empty result.
    looks_like_full_document = bool(
        re.search(
            r"<\s*(?:html|head|body)\b",
            lowered,
            re.IGNORECASE,
        )
    )

    if looks_like_full_document:
        raise LinkedInUnexpectedResponse(
            "LinkedIn returned a full document without recognizable "
            "job-search-card elements. The result is inconclusive."
        )

    previous_was_short = (
        previous_page_card_count is not None
        and 0 < int(previous_page_card_count) < PAGE_SIZE
    )

    # Positive evidence only: a short previous page plus a fragment with
    # no visible text at all. Anything carrying visible text remains
    # inconclusive.
    if previous_was_short and not _fragment_has_visible_text(
        stripped
    ):
        return "terminal_empty"

    raise LinkedInUnexpectedResponse(
        "LinkedIn returned non-empty HTML without recognizable "
        "job-search-card elements. The result is inconclusive."
    )


# ============================================================
# SEARCH CARD PARSER
# ============================================================


def extract_job_id_from_card(card):
    urn = card.get("data-entity-urn")

    if urn:
        match = re.search(
            r"jobPosting:(\d+)",
            urn,
        )
        if match:
            return match.group(1)

    link = card.select_one(
        "a.base-card__full-link"
    )

    if link:
        return extract_job_id_from_url(
            link.get("href")
        )

    return None


def parse_search_results(
    html_content,
    requested_fresh_seconds=None,
    under_10=False,
    easy_apply=False,
    observed_at_epoch=None,
):
    if observed_at_epoch is None:
        observed_at_epoch = time.time()

    soup = BeautifulSoup(
        html_content,
        "html.parser",
    )

    jobs = []

    for card in soup.select(
        "div.job-search-card"
    ):
        job_id = extract_job_id_from_card(card)
        if not job_id:
            continue

        title_el = card.select_one(
            "h3.base-search-card__title"
        )

        title = clean_text(
            title_el.get_text(" ", strip=True)
            if title_el
            else None
        )

        job_link = card.select_one(
            "a.base-card__full-link"
        )

        job_url = (
            clean_url(job_link.get("href"))
            if job_link
            else None
        )

        company_el = card.select_one(
            "a.hidden-nested-link"
        )

        company = None
        company_url = None

        if company_el:
            company = clean_text(
                company_el.get_text(" ", strip=True)
            )
            company_url = clean_url(
                company_el.get("href")
            )

        if not company:
            subtitle_el = card.select_one(
                "h4.base-search-card__subtitle"
            )
            if subtitle_el:
                company = clean_text(
                    subtitle_el.get_text(" ", strip=True)
                )

        location_el = card.select_one(
            "span.job-search-card__location"
        )

        location = clean_text(
            location_el.get_text(" ", strip=True)
            if location_el
            else None
        )

        time_el = card.select_one(
            "time.job-search-card__listdate, "
            "time.job-search-card__listdate--new"
        )

        posted = None
        posted_date = None

        if time_el:
            posted = clean_text(
                time_el.get_text(" ", strip=True)
            )
            posted_date = time_el.get("datetime")

        badge_el = card.select_one(
            ".job-posting-benefits__text"
        )

        linkedin_badge = clean_text(
            badge_el.get_text(" ", strip=True)
            if badge_el
            else None
        )

        logo_el = card.select_one(
            ".search-entity-media img"
        )

        company_logo = None

        if logo_el:
            company_logo = (
                logo_el.get("data-delayed-url")
                or logo_el.get("src")
            )

        if company_logo:
            company_logo = html.unescape(
                company_logo
            )

        row = card.get("data-row")

        try:
            row = int(row)
        except (TypeError, ValueError):
            row = None

        job = {
            "source": "linkedin",
            "job_id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "posted_date": posted_date,
            "linkedin_badge": linkedin_badge,
            "under_10_filter_requested": bool(under_10),
            "under_10_filter_matched": (
                True if under_10 else None
            ),
            "under_10_filter_source": (
                "linkedin_f_EA_EARLY_APPLICANT"
                if under_10
                else None
            ),
            "under_10_applicants": None,
            "under_10_exact_count_verified": False,
            "easy_apply_filter_requested": bool(easy_apply),
            "easy_apply_filter_matched": (
                True if easy_apply else None
            ),
            "job_url": job_url,
            "company_url": company_url,
            "company_logo": company_logo,
            "linkedin_row": row,
        }

        record_posted_observation(
            job,
            posted,
            source="linkedin_search_card_relative_display",
            observed_at_epoch=observed_at_epoch,
        )

        evaluate_job_freshness(
            job,
            requested_fresh_seconds,
            now_epoch=observed_at_epoch,
        )

        jobs.append(job)

    return jobs


def fetch_search_page(
    session,
    keywords,
    location,
    start,
    server_window_seconds,
    requested_fresh_seconds,
    under_10,
    easy_apply,
    sort_mode,
    previous_page_card_count=None,
    unexpected_retries=DEFAULT_UNEXPECTED_RESPONSE_RETRIES,
):
    params = build_search_params(
        keywords=keywords,
        location=location,
        start=start,
        server_window_seconds=server_window_seconds,
        under_10=under_10,
        easy_apply=easy_apply,
        sort_mode=sort_mode,
    )

    # HTTP 200 interstitials/soft-block pages are a different failure
    # mode from 429. Search responses are NOT marked successful by
    # safe_get() until their body passes semantic validation. This is
    # important: repeated soft limits must escalate 15 -> 30 -> 60s
    # rather than being reset by each transport-level HTTP 200.
    total_semantic_attempts = max(
        1,
        int(unexpected_retries) + 1,
    )

    last_error = None

    for semantic_attempt in range(
        1,
        total_semantic_attempts + 1,
    ):
        response = safe_get(
            session=session,
            url=SEARCH_URL,
            params=params,
            attempts=DEFAULT_RATE_MAX_ATTEMPTS,
            mark_success=False,
        )

        try:
            response_kind = classify_search_response_html(
                response.text,
                previous_page_card_count=previous_page_card_count,
            )
        except LinkedInUnexpectedResponse as exc:
            last_error = exc

            if semantic_attempt >= total_semantic_attempts:
                raise

            controller = _rate_controller(session)
            delay = controller.on_soft_limit()

            print(
                "  LinkedIn returned an unexpected 200 response. "
                f"Soft-limit recovery {semantic_attempt}/"
                f"{total_semantic_attempts - 1}; "
                f"cooldown about {delay:.1f}s."
            )
            # The next safe_get() honors the adaptive cooldown.
            continue

        controller = _rate_controller(session)
        controller.on_success()

        if semantic_attempt > 1:
            controller.on_soft_limit_recovered()
            print(
                "  Soft-limit recovery succeeded on semantic "
                f"attempt {semantic_attempt}."
            )

        session.scout_last_search_response_kind = response_kind

        if response_kind in {"empty", "terminal_empty"}:
            if response_kind == "terminal_empty":
                print(
                    "  End-of-results detected after a short final "
                    "page; treating benign fragment as exhaustion."
                )
            return []

        observed_at_epoch = time.time()

        return parse_search_results(
            response.text,
            requested_fresh_seconds=requested_fresh_seconds,
            under_10=under_10,
            easy_apply=easy_apply,
            observed_at_epoch=observed_at_epoch,
        )

    raise LinkedInUnexpectedResponse(
        str(last_error)
        if last_error
        else "Unexpected search response."
    )


# ============================================================
# DETAIL HTML CACHE
# ============================================================


def fetch_detail_html(
    session,
    job_id,
    detail_html_cache,
    attempts=3,
):
    """
    Cache both HTML and fetch timestamp. The timestamp matters because
    relative posting age must be tied to when it was observed.
    """
    if job_id in detail_html_cache:
        return detail_html_cache[job_id]

    response = safe_get(
        session=session,
        url=DETAIL_URL.format(job_id=job_id),
        attempts=attempts,
        mark_success=False,
    )

    # Semantic validation: HTTP 200 challenge/authwall/interstitial
    # bodies must not reset the adaptive rate controller or be cached
    # as valid detail content.
    stripped = (response.text or "").strip()
    if stripped:
        lowered = stripped.lower()
        for marker in _INTERSTITIAL_MARKERS:
            if marker in lowered:
                raise LinkedInUnexpectedResponse(
                    "Detail response looks like an "
                    f"interstitial/block page ({marker})."
                )

    controller = _rate_controller(session)
    controller.on_success()

    payload = {
        "html": response.text,
        "fetched_at_epoch": time.time(),
    }

    detail_html_cache[job_id] = payload
    return payload


# ============================================================
# LIGHTWEIGHT FRESHNESS VERIFICATION
# ============================================================


def parse_detail_posted_age(
    html_content,
    observed_at_epoch=None,
):
    if observed_at_epoch is None:
        observed_at_epoch = time.time()

    soup = BeautifulSoup(
        html_content,
        "html.parser",
    )

    posted_el = soup.select_one(
        "span.posted-time-ago__text"
    )

    posted = clean_text(
        posted_el.get_text(" ", strip=True)
        if posted_el
        else None
    )

    job = {}

    record_posted_observation(
        job,
        posted,
        source="linkedin_job_detail_relative_display",
        observed_at_epoch=observed_at_epoch,
    )

    return job


def verify_job_freshness(
    session,
    job_id,
    requested_fresh_seconds,
    detail_html_cache,
):
    try:
        payload = fetch_detail_html(
            session=session,
            job_id=job_id,
            detail_html_cache=detail_html_cache,
            attempts=3,
        )

    except LinkedInRateLimited as exc:
        return {
            "filter_passed": None,
            "error": str(exc),
            "source": "linkedin_detail_rate_limited",
        }

    except LinkedInError as exc:
        return {
            "filter_passed": None,
            "error": str(exc),
            "source": "linkedin_detail_failed",
        }

    observation = parse_detail_posted_age(
        payload["html"],
        observed_at_epoch=payload["fetched_at_epoch"],
    )

    passed = evaluate_job_freshness(
        observation,
        requested_fresh_seconds,
        now_epoch=payload["fetched_at_epoch"],
    )

    return {
        "filter_passed": passed,
        "observation": observation,
        "error": None,
        "source": observation.get("freshness_source"),
    }


# ============================================================
# SEARCH SCANNER
# ============================================================


def _error_record(exc, page_index, start):
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "page_index": page_index,
        "start": start,
        "at": utc_iso(),
    }


def scan_search(
    session,
    keywords,
    location,
    requested_fresh_seconds,
    server_window_seconds,
    under_10,
    easy_apply,
    sort_mode,
    max_jobs,
    max_pages,
    page_delay,
    detail_html_cache,
    start_offset=0,
    checkpoint_file=None,
):
    """
    Paginate until one of these happens:

      - max_jobs accepted
      - max_pages reached
      - LinkedIn returns an empty page
      - an identical page repeats
      - a real request/response error occurs

    There is deliberately NO "two stale pages" early-stop heuristic.

    max_pages is a per-run budget: with start_offset > 0, at most
    max_pages pages are attempted starting at start_offset, not an
    absolute LinkedIn page-number ceiling.
    """
    jobs = []
    seen_job_ids = set()
    seen_page_signatures = set()

    stats = {
        "pages_attempted": 0,
        "pages_attempted_this_run": 0,
        "pages_succeeded": 0,
        "cards_received": 0,
        "fresh_accepted": 0,
        "stale_dropped": 0,
        "unknown_age_cards": 0,
        "unknown_age_verified": 0,
        "unknown_age_dropped": 0,
        "duplicates": 0,
        "errors": [],
        "stop_reason": None,
        "search_status": None,
        "search_complete": False,
        "truncated": False,
        "start_offset": start_offset,
        "last_successful_start": None,
        "failed_start": None,
        "failed_page": None,
        "resume_start": None,
        "circuit_breaker_opened": False,
        "circuit_breaker_reason": None,
    }

    start = start_offset
    previous_page_card_count = None

    try:
        for page_index in range(max_pages):
            if len(jobs) >= max_jobs:
                stats["stop_reason"] = "max_jobs"
                stats["truncated"] = True
                break

            stats["pages_attempted"] += 1
            stats["pages_attempted_this_run"] += 1

            linkedin_page = start // PAGE_SIZE + 1

            print(
                f"\nFetching search page start={start} "
                f"(run page {page_index + 1}/{max_pages}, "
                f"LinkedIn page {linkedin_page})..."
            )

            try:
                page_jobs = fetch_search_page(
                    session=session,
                    keywords=keywords,
                    location=location,
                    start=start,
                    server_window_seconds=server_window_seconds,
                    requested_fresh_seconds=requested_fresh_seconds,
                    under_10=under_10,
                    easy_apply=easy_apply,
                    sort_mode=sort_mode,
                    previous_page_card_count=previous_page_card_count,
                )

            except LinkedInError as exc:
                stats["errors"].append(
                    _error_record(exc, page_index, start)
                )
                stats["failed_start"] = start
                stats["failed_page"] = linkedin_page

                if isinstance(exc, LinkedInRateLimited):
                    stats["stop_reason"] = (
                        "hard_rate_limit_circuit_breaker"
                    )
                    stats["circuit_breaker_opened"] = True
                    stats["circuit_breaker_reason"] = (
                        "hard_rate_limit"
                    )
                elif isinstance(exc, LinkedInUnexpectedResponse):
                    stats["stop_reason"] = (
                        "soft_limit_circuit_breaker"
                    )
                    stats["circuit_breaker_opened"] = True
                    stats["circuit_breaker_reason"] = (
                        "soft_limit"
                    )
                else:
                    stats["stop_reason"] = "request_error"

                stats["resume_start"] = start

                print(
                    "Search request failed: "
                    f"{exc.__class__.__name__}: {exc}"
                )
                break

            stats["pages_succeeded"] += 1
            stats["last_successful_start"] = start

            print(
                f"Received {len(page_jobs)} cards."
            )

            stats["cards_received"] += len(page_jobs)

            if not page_jobs:
                response_kind = getattr(
                    session,
                    "scout_last_search_response_kind",
                    "empty",
                )
                stats["stop_reason"] = (
                    "end_of_results"
                    if response_kind == "terminal_empty"
                    else "empty_page"
                )
                stats["search_complete"] = True
                break

            page_signature = tuple(
                job.get("job_id")
                for job in page_jobs
                if job.get("job_id")
            )

            if page_signature in seen_page_signatures:
                stats["stop_reason"] = "repeated_page"
                stats["truncated"] = True
                print(
                    "Repeated search page detected. "
                    "Stopping because deeper pagination is inconclusive."
                )
                break

            seen_page_signatures.add(page_signature)
            previous_page_card_count = len(page_jobs)

            accepted_on_page = 0

            for job in page_jobs:
                if len(jobs) >= max_jobs:
                    break

                job_id = job.get("job_id")
                if not job_id:
                    continue

                if job_id in seen_job_ids:
                    stats["duplicates"] += 1
                    continue

                seen_job_ids.add(job_id)

                if requested_fresh_seconds is not None:
                    passed = evaluate_job_freshness(
                        job,
                        requested_fresh_seconds,
                    )

                    if passed is False:
                        stats["stale_dropped"] += 1
                        print(
                            "  DROP stale "
                            f"{job_id}: display={job.get('posted')!r}, "
                            "approx_age="
                            f"{job.get('freshness_age_estimate_seconds_at_check')}s"
                        )
                        continue

                    if passed is None:
                        stats["unknown_age_cards"] += 1
                        print(
                            "  Age unavailable "
                            f"{job_id} -> verifying detail..."
                        )

                        verification = verify_job_freshness(
                            session=session,
                            job_id=job_id,
                            requested_fresh_seconds=requested_fresh_seconds,
                            detail_html_cache=detail_html_cache,
                        )

                        detail_passed = verification.get(
                            "filter_passed"
                        )
                        observation = verification.get(
                            "observation"
                        ) or {}

                        if observation:
                            for key, value in observation.items():
                                job[key] = value

                        if detail_passed is False:
                            stats["stale_dropped"] += 1
                            print(
                                "  DROP stale after detail verification "
                                f"{job_id}"
                            )
                            continue

                        if detail_passed is None:
                            stats["unknown_age_dropped"] += 1
                            print(
                                "  DROP unverified age "
                                f"{job_id}"
                            )
                            continue

                        stats["unknown_age_verified"] += 1
                        evaluate_job_freshness(
                            job,
                            requested_fresh_seconds,
                        )

                        print(
                            "  VERIFIED fresh by relative detail age "
                            f"{job_id}: {job.get('posted')}"
                        )

                jobs.append(job)
                accepted_on_page += 1
                stats["fresh_accepted"] += 1

            print(
                "Accepted from page: "
                f"{accepted_on_page}"
            )

            if len(jobs) >= max_jobs:
                stats["stop_reason"] = "max_jobs"
                stats["truncated"] = True
                break

            start += PAGE_SIZE

            if page_index + 1 < max_pages:
                time.sleep(page_delay)

        else:
            stats["stop_reason"] = "max_pages"
            stats["truncated"] = True
            stats["resume_start"] = start

    except KeyboardInterrupt:
        stats["stop_reason"] = "interrupted"
        stats["search_complete"] = False
        stats["resume_start"] = start
        stats["failed_start"] = start
        stats["failed_page"] = start // PAGE_SIZE + 1
        stats["search_status"] = (
            "partial"
            if stats["pages_succeeded"] > 0
            else "failed"
        )

        print(
            "\nInterrupted by user during search pagination."
        )

        if checkpoint_file:
            save_checkpoint(
                jobs,
                checkpoint_file,
                extra={
                    "search_status": stats["search_status"],
                    "search_complete": False,
                    "stop_reason": "interrupted",
                    "resume": build_resume_info(stats),
                },
            )
            print(
                f"Partial results saved to: {checkpoint_file}"
            )

        raise

    # Classify the search outcome.
    if stats["errors"]:
        stats["search_status"] = (
            "failed"
            if stats["pages_succeeded"] == 0
            else "partial"
        )
        stats["search_complete"] = False

    elif stats["stop_reason"] in {
        "empty_page",
        "end_of_results",
    }:
        stats["search_status"] = "success"
        stats["search_complete"] = True

    elif stats["stop_reason"] == "max_jobs":
        # The requested number of accepted jobs was fulfilled, even
        # though the entire upstream result set was not exhausted.
        stats["search_status"] = "success"
        stats["search_complete"] = False

    elif stats["stop_reason"] in {
        "max_pages",
        "repeated_page",
    }:
        stats["search_status"] = "partial"
        stats["search_complete"] = False

    else:
        stats["search_status"] = "partial"
        stats["search_complete"] = False

    stats["empty_result_is_conclusive"] = bool(
        stats["search_status"] == "success"
        and stats["search_complete"]
        and len(jobs) == 0
    )

    stats["circuit_breaker"] = {
        "opened": stats["circuit_breaker_opened"],
        "reason": stats["circuit_breaker_reason"],
        "failed_start": stats["failed_start"],
        "failed_page": stats["failed_page"],
    }

    return jobs[:max_jobs], stats


# ============================================================
# SEARCH ENTRY POINT
# ============================================================


def search_linkedin_jobs(
    session,
    keywords,
    location,
    max_jobs,
    posted_within_seconds,
    under_10,
    easy_apply,
    sort_mode,
    page_delay,
    max_pages,
    detail_html_cache,
    start_offset=0,
    checkpoint_file=None,
):
    server_window_seconds = choose_server_window(
        posted_within_seconds
    )

    print("\nSearching LinkedIn:")
    print(f"  Keywords:       {keywords}")
    print(f"  Location:       {location}")
    print(f"  Maximum:        {max_jobs}")
    print(f"  Max pages:      {max_pages}")
    print(f"  Sort:           {sort_mode}")

    if start_offset:
        print(
            "  Resume start:   "
            f"{start_offset} "
            f"(LinkedIn page {start_offset // PAGE_SIZE + 1})"
        )

    if posted_within_seconds is not None:
        print(
            "  Requested age:  "
            f"{posted_within_seconds}s "
            f"({posted_within_seconds / 60:g} min)"
        )
        print(
            "  Server window:  "
            f"{server_window_seconds}s "
            f"({make_tpr_value(server_window_seconds)})"
        )
        print(
            "  Freshness:      approximate relative-age cutoff; "
            "not an exact posting timestamp"
        )

    if under_10:
        print(
            "  Applicants:     LinkedIn Under-10 filter "
            "requested (f_EA=true)"
        )

    if easy_apply:
        print(
            "  Easy Apply:     ON (f_AL=true)"
        )

    jobs, stats = scan_search(
        session=session,
        keywords=keywords,
        location=location,
        requested_fresh_seconds=posted_within_seconds,
        server_window_seconds=server_window_seconds,
        under_10=under_10,
        easy_apply=easy_apply,
        sort_mode=sort_mode,
        max_jobs=max_jobs,
        max_pages=max_pages,
        page_delay=page_delay,
        detail_html_cache=detail_html_cache,
        start_offset=start_offset,
        checkpoint_file=checkpoint_file,
    )

    stats["requested_window_seconds"] = (
        posted_within_seconds
    )
    stats["server_window_seconds"] = (
        server_window_seconds
    )
    stats["server_f_TPR"] = (
        make_tpr_value(server_window_seconds)
        if server_window_seconds is not None
        else None
    )

    return jobs, stats


# ============================================================
# FULL JOB DETAIL PARSER
# ============================================================


def parse_job_detail(
    html_content,
    fallback_job_id=None,
    observed_at_epoch=None,
):
    if observed_at_epoch is None:
        observed_at_epoch = time.time()

    soup = BeautifulSoup(
        html_content,
        "html.parser",
    )

    title_el = soup.select_one(
        "h2.topcard__title"
    )

    title = clean_text(
        title_el.get_text(" ", strip=True)
        if title_el
        else None
    )

    job_link = soup.select_one(
        "a.topcard__link"
    )

    job_url = (
        clean_url(job_link.get("href"))
        if job_link
        else None
    )

    job_id = (
        extract_job_id_from_url(job_url)
        or fallback_job_id
    )

    company_el = soup.select_one(
        "a.topcard__org-name-link"
    )

    company = None
    company_url = None

    if company_el:
        company = clean_text(
            company_el.get_text(" ", strip=True)
        )
        company_url = clean_url(
            company_el.get("href")
        )

    location = None

    flavor_row = soup.select_one(
        ".top-card-layout__second-subline "
        ".topcard__flavor-row"
    )

    if flavor_row:
        location_el = flavor_row.select_one(
            ".topcard__flavor--bullet"
        )
        if location_el:
            location = clean_text(
                location_el.get_text(" ", strip=True)
            )

    posted_el = soup.select_one(
        "span.posted-time-ago__text"
    )

    posted = clean_text(
        posted_el.get_text(" ", strip=True)
        if posted_el
        else None
    )

    applicant_el = soup.select_one(
        ".num-applicants__caption"
    )

    applicants = clean_text(
        applicant_el.get_text(" ", strip=True)
        if applicant_el
        else None
    )

    applicant_info = parse_applicant_information(
        applicants
    )

    logo_el = soup.select_one(
        ".top-card-layout img.artdeco-entity-image"
    )

    company_logo = None

    if logo_el:
        company_logo = (
            logo_el.get("data-delayed-url")
            or logo_el.get("src")
        )

    if company_logo:
        company_logo = html.unescape(
            company_logo
        )

    description_el = soup.select_one(
        ".description__text "
        ".show-more-less-html__markup"
    )

    description = (
        clean_multiline_text(description_el)
        if description_el
        else None
    )

    description_html = (
        str(description_el)
        if description_el
        else None
    )

    criteria = {}

    for item in soup.select(
        "li.description__job-criteria-item"
    ):
        header_el = item.select_one(
            ".description__job-criteria-subheader"
        )
        value_el = item.select_one(
            ".description__job-criteria-text"
        )

        if not header_el or not value_el:
            continue

        key = clean_text(
            header_el.get_text(" ", strip=True)
        )
        value = clean_text(
            value_el.get_text(" ", strip=True)
        )

        if key:
            criteria[key.lower()] = value

    result = {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "applicants": applicants,
        "applicant_count": applicant_info[
            "applicant_count"
        ],
        "applicant_count_exact": applicant_info[
            "applicant_count_exact"
        ],
        "applicant_count_minimum": applicant_info[
            "applicant_count_minimum"
        ],
        "applicant_count_relation": applicant_info[
            "applicant_count_relation"
        ],
        "seniority_level": criteria.get(
            "seniority level"
        ),
        "employment_type": criteria.get(
            "employment type"
        ),
        "job_function": criteria.get(
            "job function"
        ),
        "industries": criteria.get(
            "industries"
        ),
        "description": description,
        "description_html": description_html,
        "job_url": job_url,
        "company_url": company_url,
        "company_logo": company_logo,
    }

    record_posted_observation(
        result,
        posted,
        source="linkedin_job_detail_relative_display",
        observed_at_epoch=observed_at_epoch,
    )

    return result


# ============================================================
# MERGE / UNDER-10 EVIDENCE
# ============================================================


def apply_under_10_evidence(
    result,
    under_10_requested,
):
    exact_count = result.get("applicant_count")
    exact = result.get(
        "applicant_count_exact",
        False,
    )
    minimum = result.get(
        "applicant_count_minimum"
    )

    result["under_10_filter_requested"] = bool(
        under_10_requested
    )

    if under_10_requested:
        result.setdefault(
            "under_10_filter_matched",
            True,
        )
        result.setdefault(
            "under_10_filter_source",
            "linkedin_f_EA_EARLY_APPLICANT",
        )

    result["under_10_exact_count_verified"] = False

    if exact and exact_count is not None:
        result["under_10_applicants"] = (
            exact_count < 10
        )
        result["under_10_exact_count_verified"] = True
        result["under_10_evidence_source"] = (
            "exact_applicant_count"
        )
        return result

    if minimum is not None:
        # A minimum of 10 or more proves it is not under 10.
        if minimum >= 10:
            result["under_10_applicants"] = False
            result["under_10_evidence_source"] = (
                "applicant_count_minimum"
            )
            return result

        # Minimum below 10 does not prove the final count is below 10.
        result["under_10_applicants"] = None
        result["under_10_evidence_source"] = (
            "applicant_count_minimum_inconclusive"
        )
        return result

    # No independent count evidence. Preserve the LinkedIn filter match
    # separately instead of pretending the count was verified.
    result["under_10_applicants"] = None
    result["under_10_evidence_source"] = None

    return result


def merge_job_data(
    search_job,
    detail_job,
    posted_within_seconds,
    under_10,
):
    result = dict(search_job)

    if detail_job:
        for field, value in detail_job.items():
            if value is not None:
                result[field] = value

    evaluate_job_freshness(
        result,
        posted_within_seconds,
    )

    apply_under_10_evidence(
        result,
        under_10_requested=under_10,
    )

    return result


# ============================================================
# CHECKPOINT
# ============================================================


def _public_job_copy(job):
    result = dict(job)
    result.pop(
        "_freshness_observed_at_epoch",
        None,
    )
    result.pop(
        "_freshness_observed_monotonic",
        None,
    )
    return result


def build_resume_info(search_stats):
    """
    Build the machine-readable resume block from scan_search() stats.

    resume.start always points at the offset that must be retried, never
    at an offset that was already successfully processed.
    """
    resume_start = search_stats.get("resume_start")

    if resume_start is None:
        return {
            "available": False,
            "start": None,
            "linkedin_page": None,
            "reason": None,
        }

    return {
        "available": True,
        "start": resume_start,
        "linkedin_page": resume_start // PAGE_SIZE + 1,
        "reason": search_stats.get("stop_reason"),
    }


def save_checkpoint(
    jobs,
    filename,
    extra=None,
):
    if not filename:
        return

    payload = {
        "saved_at": utc_iso(),
        "total_jobs": len(jobs),
        "jobs": [
            _public_job_copy(job)
            for job in jobs
        ],
    }

    if extra:
        payload.update(extra)

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# FULL DETAIL ENRICHMENT
# ============================================================


def enrich_jobs_with_details(
    session,
    jobs,
    posted_within_seconds,
    under_10,
    detail_delay,
    detail_html_cache,
    checkpoint_file=None,
    checkpoint_extra=None,
):
    final_jobs = []
    total = len(jobs)
    rate_limited = False

    stats = {
        "requested": total,
        "detail_fetched": 0,
        "detail_failed": 0,
        "detail_rate_limited": False,
        # Time-based drops only. Applicant-evidence drops are tracked
        # separately in under_10_contradictions_dropped so the two
        # reasons are never confused with each other.
        "freshness_expired_during_enrichment": 0,
        "freshness_unknown_during_enrichment": 0,
        "under_10_contradictions_dropped": 0,
    }

    for index, search_job in enumerate(
        jobs,
        start=1,
    ):
        job_id = search_job.get("job_id")

        print(
            f"\n[{index}/{total}] "
            f"{job_id} - {search_job.get('title')}"
        )

        detail_job = None

        if not rate_limited:
            try:
                payload = fetch_detail_html(
                    session=session,
                    job_id=job_id,
                    detail_html_cache=detail_html_cache,
                    attempts=2,
                )

                detail_job = parse_job_detail(
                    payload["html"],
                    fallback_job_id=job_id,
                    observed_at_epoch=payload[
                        "fetched_at_epoch"
                    ],
                )

                stats["detail_fetched"] += 1
                print("  Detail fetched.")

            except LinkedInRateLimited:
                rate_limited = True
                stats["detail_rate_limited"] = True
                print(
                    "  LinkedIn detail rate limit reached."
                )
                print(
                    "  Remaining already-filtered search jobs "
                    "will stay search-only."
                )

            except LinkedInError as exc:
                stats["detail_failed"] += 1
                print(
                    "  Detail skipped: "
                    f"{exc.__class__.__name__}: {exc}"
                )

        merged = merge_job_data(
            search_job=search_job,
            detail_job=detail_job,
            posted_within_seconds=posted_within_seconds,
            under_10=under_10,
        )

        # Re-evaluate at the current time, not the original search time.
        if posted_within_seconds is not None:
            passed = evaluate_job_freshness(
                merged,
                posted_within_seconds,
            )

            if passed is False:
                stats[
                    "freshness_expired_during_enrichment"
                ] += 1
                print(
                    "  DROP: no longer passes the requested "
                    "relative-age freshness cutoff (expired)."
                )
                continue

            if passed is None:
                stats[
                    "freshness_unknown_during_enrichment"
                ] += 1
                print(
                    "  DROP: freshness could not be determined "
                    "at enrichment time."
                )
                continue

        # Only independent count evidence can contradict the upstream
        # f_EA filter match.
        if (
            under_10
            and merged.get("under_10_applicants") is False
        ):
            stats[
                "under_10_contradictions_dropped"
            ] += 1
            print(
                "  DROP: applicant count evidence contradicts "
                "the Under-10 filter match."
            )
            continue

        if under_10:
            if merged.get(
                "under_10_exact_count_verified"
            ):
                print(
                    "  Exact applicants: "
                    f"{merged.get('applicant_count')}"
                )
            else:
                print(
                    "  LinkedIn Under-10 filter matched; "
                    "exact count not independently verified."
                )

        print(
            "  Posted: "
            f"{merged.get('posted')}"
        )

        final_jobs.append(merged)

        if checkpoint_file:
            save_checkpoint(
                final_jobs,
                checkpoint_file,
                extra=checkpoint_extra,
            )

        if not rate_limited and index < total:
            time.sleep(detail_delay)

    stats["kept"] = len(final_jobs)
    stats["status"] = (
        "partial"
        if stats["detail_rate_limited"]
        or stats["detail_failed"] > 0
        else "success"
    )

    return final_jobs, stats


# ============================================================
# FINAL OUTPUT FRESHNESS PASS
# ============================================================


def finalize_jobs_for_output(
    jobs,
    posted_within_seconds,
):
    """
    Final freshness pass immediately before output.

    Returns (final_jobs, drop_stats) where drop_stats separates jobs
    that expired (time-based) from jobs whose freshness could not be
    determined (unknown), so callers never have to infer removal
    reasons by subtraction.
    """
    if posted_within_seconds is None:
        return [
            _public_job_copy(job)
            for job in jobs
        ], {"expired": 0, "unknown": 0}

    now_epoch = time.time()
    final_jobs = []
    expired = 0
    unknown = 0

    for job in jobs:
        passed = evaluate_job_freshness(
            job,
            posted_within_seconds,
            now_epoch=now_epoch,
        )

        if passed is False:
            expired += 1
            continue

        if passed is None:
            unknown += 1
            continue

        final_jobs.append(
            _public_job_copy(job)
        )

    return final_jobs, {
        "expired": expired,
        "unknown": unknown,
    }


# ============================================================
# PUBLIC CONNECTOR FUNCTION
# ============================================================


def fetch_linkedin_jobs(
    keywords,
    location,
    max_jobs=50,
    posted_within=None,
    under_10=False,
    easy_apply=False,
    sort_mode="newest",
    fetch_details=True,
    page_delay=0.0,
    detail_delay=0.0,
    max_pages=20,
    checkpoint_file=None,
    start=0,
    rate_min_interval=DEFAULT_RATE_MIN_INTERVAL,
    rate_max_interval=DEFAULT_RATE_MAX_INTERVAL,
    rate_cooldown_base=DEFAULT_RATE_COOLDOWN_BASE,
    rate_cooldown_cap=DEFAULT_RATE_COOLDOWN_CAP,
    rate_burst_size=DEFAULT_RATE_BURST_SIZE,
    rate_burst_rest=DEFAULT_RATE_BURST_REST,
):
    if max_jobs <= 0:
        raise ValueError(
            "max_jobs must be greater than zero."
        )

    if max_pages <= 0:
        raise ValueError(
            "max_pages must be greater than zero."
        )

    start_offset = validate_start_offset(start)

    posted_within_seconds = (
        parse_duration(posted_within)
        if posted_within
        else None
    )

    server_window_seconds = choose_server_window(
        posted_within_seconds
    )

    session = create_session(
        rate_min_interval=rate_min_interval,
        rate_max_interval=rate_max_interval,
        rate_cooldown_base=rate_cooldown_base,
        rate_cooldown_cap=rate_cooldown_cap,
        rate_burst_size=rate_burst_size,
        rate_burst_rest=rate_burst_rest,
    )
    detail_html_cache = {}

    try:
        search_jobs, search_stats = search_linkedin_jobs(
            session=session,
            keywords=keywords,
            location=location,
            max_jobs=max_jobs,
            posted_within_seconds=posted_within_seconds,
            under_10=under_10,
            easy_apply=easy_apply,
            sort_mode=sort_mode,
            page_delay=page_delay,
            max_pages=max_pages,
            detail_html_cache=detail_html_cache,
            start_offset=start_offset,
            checkpoint_file=checkpoint_file,
        )

        search_results_found = len(search_jobs)
        jobs = search_jobs

        resume_info = build_resume_info(search_stats)

        # A search-stage checkpoint ensures --no-details runs (and any
        # run that opens the circuit breaker before enrichment starts)
        # still leave a resumable partial state on disk, not just the
        # per-job checkpoints enrichment writes below.
        checkpoint_extra = {
            "search_status": search_stats["search_status"],
            "search_complete": search_stats["search_complete"],
            "stop_reason": search_stats["stop_reason"],
            "resume": resume_info,
            "circuit_breaker": search_stats.get(
                "circuit_breaker",
                {
                    "opened": False,
                    "reason": None,
                    "failed_start": None,
                    "failed_page": None,
                },
            ),
            "failed_start": search_stats.get("failed_start"),
            "last_successful_start": search_stats.get(
                "last_successful_start"
            ),
            "rate_limit": _rate_controller(session).snapshot(),
        }

        if checkpoint_file:
            save_checkpoint(
                search_jobs,
                checkpoint_file,
                extra=checkpoint_extra,
            )

        enrichment_stats = {
            "status": "skipped",
            "requested": 0,
            "kept": len(jobs),
            "freshness_expired_during_enrichment": 0,
            "freshness_unknown_during_enrichment": 0,
            "under_10_contradictions_dropped": 0,
        }

        if fetch_details and jobs:
            jobs, enrichment_stats = enrich_jobs_with_details(
                session=session,
                jobs=jobs,
                posted_within_seconds=posted_within_seconds,
                under_10=under_10,
                detail_delay=detail_delay,
                detail_html_cache=detail_html_cache,
                checkpoint_file=checkpoint_file,
                checkpoint_extra=checkpoint_extra,
            )

        final_jobs, finalize_drop_stats = (
            finalize_jobs_for_output(
                jobs,
                posted_within_seconds,
            )
        )

        expired_before_output = (
            enrichment_stats.get(
                "freshness_expired_during_enrichment", 0
            )
            + finalize_drop_stats["expired"]
        )
        final_unknown_freshness_dropped = (
            enrichment_stats.get(
                "freshness_unknown_during_enrichment", 0
            )
            + finalize_drop_stats["unknown"]
        )
        applicant_filter_invalidated = enrichment_stats.get(
            "under_10_contradictions_dropped", 0
        )

        effective_filters = {
            "sortBy": (
                "DD" if sort_mode == "newest" else "R"
            )
        }

        if server_window_seconds is not None:
            effective_filters["f_TPR"] = make_tpr_value(
                server_window_seconds
            )

        if under_10:
            effective_filters["f_EA"] = "true"

        if easy_apply:
            effective_filters["f_AL"] = "true"

        search_status = search_stats[
            "search_status"
        ]

        # Recompute zero_conclusive after finalization: a search can
        # find jobs which later expire before final output.  A completed
        # search that accepted jobs during pagination but produced zero
        # final output jobs is still a conclusive zero.
        zero_conclusive = (
            search_stats["search_status"] == "success"
            and search_stats["search_complete"] is True
            and len(final_jobs) == 0
        )

        return {
            "source": "linkedin",
            "status": search_status,
            "search_status": search_status,
            "search_complete": search_stats[
                "search_complete"
            ],
            "search_stop_reason": search_stats[
                "stop_reason"
            ],
            # "stop_reason" is the name used by the status-semantics spec;
            # keep both keys identical for backward compatibility.
            "stop_reason": search_stats[
                "stop_reason"
            ],
            "search_errors": search_stats[
                "errors"
            ],
            "empty_result_is_conclusive": search_stats[
                "empty_result_is_conclusive"
            ],
            # Recomputed after finalize_jobs_for_output(): all accepted
            # jobs may have expired, making this a conclusive zero even
            # though the search-stage list was non-empty.
            "zero_conclusive": zero_conclusive,
            "query": {
                "keywords": keywords,
                "location": location,
                "max_jobs": max_jobs,
                "max_pages": max_pages,
                "start": start_offset,
                "posted_within": posted_within,
                "posted_within_seconds": (
                    posted_within_seconds
                ),
                "server_window_seconds": (
                    server_window_seconds
                ),
                "under_10_filter_requested": (
                    under_10
                ),
                "easy_apply": easy_apply,
                "sort": sort_mode,
                "fetch_details": fetch_details,
            },
            "scan": {
                "start_offset": start_offset,
                "pages_attempted": search_stats.get(
                    "pages_attempted_this_run"
                ),
                "last_successful_start": search_stats.get(
                    "last_successful_start"
                ),
                "failed_start": search_stats.get(
                    "failed_start"
                ),
            },
            "resume": resume_info,
            "circuit_breaker": search_stats.get(
                "circuit_breaker",
                {
                    "opened": False,
                    "reason": None,
                    "failed_start": None,
                    "failed_page": None,
                },
            ),
            "linkedin_filters": effective_filters,
            "freshness_policy": {
                "mode": (
                    "relative_display_plus_elapsed_time"
                    if posted_within_seconds is not None
                    else None
                ),
                "exact": False,
                "note": (
                    "LinkedIn public HTML exposes a relative display "
                    "age, not an exact posting timestamp. The connector "
                    "accounts for elapsed runtime but does not claim an "
                    "exact second-level posting cutoff."
                    if posted_within_seconds is not None
                    else None
                ),
                "unknown_age_policy": (
                    "verify_detail_then_drop_if_still_unknown"
                    if posted_within_seconds is not None
                    else None
                ),
                "sub_hour_server_window": "r3600",
                "expired_at_final_output": (
                    finalize_drop_stats["expired"]
                ),
            },
            "under_10_policy": {
                "filter_mapping": (
                    "f_EA=EARLY_APPLICANT"
                    if under_10
                    else None
                ),
                "filter_match_is_exact_count_proof": False,
                "exact_count_is_independent_evidence": True,
            },
            "search_stats": search_stats,
            "enrichment_stats": enrichment_stats,
            "drop_reasons": {
                "expired_before_output": expired_before_output,
                "applicant_filter_invalidated": (
                    applicant_filter_invalidated
                ),
                "final_unknown_freshness_dropped": (
                    final_unknown_freshness_dropped
                ),
            },
            "rate_limit_policy": {
                "mode": "adaptive_conservative",
                "upstream_success_guaranteed": False,
                "note": (
                    "The connector can pace, cool down, retry, and report "
                    "throttling safely, but LinkedIn controls upstream "
                    "acceptance and can still reject public guest requests."
                ),
                **_rate_controller(session).snapshot(),
                "hard_rate_limit_events": (
                    _rate_controller(session).rate_limit_events
                ),
                # Spec alias: singular "recovered" vs snapshot's plural
                # "recoveries". Keep both identical.
                "soft_limit_recovered": (
                    _rate_controller(session).soft_limit_recoveries
                ),
                "final_rate_gap_seconds": round(
                    _rate_controller(session).current_interval,
                    3,
                ),
                "circuit_breaker_opened": search_stats.get(
                    "circuit_breaker_opened", False
                ),
                "circuit_breaker_reason": search_stats.get(
                    "circuit_breaker_reason"
                ),
            },
            "fetched_at": utc_iso(),
            "search_results_found": search_results_found,
            "expired_before_output": expired_before_output,
            "total_jobs": len(final_jobs),
            "jobs": final_jobs,
        }

    finally:
        session.close()


# ============================================================
# JSON OUTPUT
# ============================================================


def save_json(data, filename):
    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\nSaved to: {filename}")


# ============================================================
# CLI
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description=(
            "SCOUTJOBS LinkedIn Jobs Connector"
        )
    )

    parser.add_argument(
        "--keywords",
        default="Software Engineer",
        help="Job title / keywords",
    )
    parser.add_argument(
        "--location",
        default="India",
        help="Job location",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=50,
        help="Maximum accepted jobs",
    )
    parser.add_argument(
        "--posted-within",
        default=None,
        help=(
            "Freshness window: 5m, 10m, 30m, "
            "1h, 24h, 7d, etc."
        ),
    )
    parser.add_argument(
        "--under-10",
        action="store_true",
        help=(
            "Request LinkedIn's Under 10 Applicants filter "
            "(f_EA=true). This is a filter match, not an "
            "independent exact-count verification."
        ),
    )
    parser.add_argument(
        "--easy-apply",
        action="store_true",
        help="LinkedIn Easy Apply (f_AL=true)",
    )
    parser.add_argument(
        "--sort",
        choices=["newest", "relevance"],
        default="newest",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help=(
            "Skip full description/criteria enrichment. "
            "Unknown freshness age can still trigger a lightweight "
            "public detail request."
        ),
    )
    parser.add_argument(
        "--output",
        default="linkedin_jobs.json",
    )
    parser.add_argument(
        "--page-delay",
        type=float,
        default=0.0,
        help=(
            "Optional extra delay after each search page. "
            "Adaptive global pacing is already enabled."
        ),
    )
    parser.add_argument(
        "--detail-delay",
        type=float,
        default=0.0,
        help=(
            "Optional extra delay between detail enrichments. "
            "Adaptive global pacing is already enabled."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help=(
            "Resume pagination from this LinkedIn start offset "
            "(must be a multiple of 10). --max-pages is a per-run "
            "budget beginning at this offset, not an absolute page "
            "ceiling. Default: 0"
        ),
    )
    parser.add_argument(
        "--rate-min-interval",
        type=float,
        default=DEFAULT_RATE_MIN_INTERVAL,
        help=(
            "Minimum seconds between LinkedIn requests. "
            "Default: 3.0"
        ),
    )
    parser.add_argument(
        "--rate-max-interval",
        type=float,
        default=DEFAULT_RATE_MAX_INTERVAL,
        help=(
            "Maximum adaptive spacing after throttling. "
            "Default: 15.0"
        ),
    )
    parser.add_argument(
        "--rate-cooldown-base",
        type=float,
        default=DEFAULT_RATE_COOLDOWN_BASE,
        help=(
            "Initial cooldown after a rate-limit/soft-limit signal. "
            "Default: 15.0"
        ),
    )
    parser.add_argument(
        "--rate-cooldown-cap",
        type=float,
        default=DEFAULT_RATE_COOLDOWN_CAP,
        help=(
            "Maximum connector-generated cooldown after repeated limiting. "
            "An explicit LinkedIn Retry-After is never shortened. "
            "Default: 90.0"
        ),
    )
    parser.add_argument(
        "--rate-burst-size",
        type=int,
        default=DEFAULT_RATE_BURST_SIZE,
        help=(
            "Take a proactive rest after this many requests. "
            "Use 0 to disable. Default: 4"
        ),
    )
    parser.add_argument(
        "--rate-burst-rest",
        type=float,
        default=DEFAULT_RATE_BURST_REST,
        help=(
            "Seconds to rest after each proactive request burst. "
            "Default: 8.0"
        ),
    )

    args = parser.parse_args()

    print(
        "\n"
        "============================================\n"
        "        SCOUTJOBS LINKEDIN CONNECTOR\n"
        "============================================"
    )

    checkpoint_file = (
        args.output + ".partial.json"
    )

    try:
        data = fetch_linkedin_jobs(
            keywords=args.keywords,
            location=args.location,
            max_jobs=args.max_jobs,
            posted_within=args.posted_within,
            under_10=args.under_10,
            easy_apply=args.easy_apply,
            sort_mode=args.sort,
            fetch_details=not args.no_details,
            page_delay=args.page_delay,
            detail_delay=args.detail_delay,
            max_pages=args.max_pages,
            checkpoint_file=checkpoint_file,
            start=args.start,
            rate_min_interval=args.rate_min_interval,
            rate_max_interval=args.rate_max_interval,
            rate_cooldown_base=args.rate_cooldown_base,
            rate_cooldown_cap=args.rate_cooldown_cap,
            rate_burst_size=args.rate_burst_size,
            rate_burst_rest=args.rate_burst_rest,
        )

    except KeyboardInterrupt:
        print("\nStopped by user.")
        print(
            "Successfully enriched jobs may remain in:"
        )
        print(checkpoint_file)
        return 130

    except ValueError as exc:
        print(f"\nERROR: {exc}")
        return 2

    except LinkedInError as exc:
        print(
            "\nLinkedIn connector error: "
            f"{exc.__class__.__name__}: {exc}"
        )
        return 2

    save_json(data, args.output)

    print(
        "\n============================================"
    )
    print(
        "SEARCH STATUS:  "
        f"{data['search_status']}"
    )
    print(
        "SEARCH COMPLETE: "
        f"{data['search_complete']}"
    )
    print(
        "STOP REASON:    "
        f"{data['search_stop_reason']}"
    )
    print(
        "SEARCH RESULTS: "
        f"{data['search_results_found']}"
    )
    print(
        "FINAL JOBS:     "
        f"{data['total_jobs']}"
    )
    print(
        "ZERO CONCLUSIVE: "
        f"{data['empty_result_is_conclusive']}"
    )
    rate = data.get("rate_limit_policy", {})
    print(
        "RATE EVENTS:     "
        f"{rate.get('rate_limit_events', 0)}"
    )
    print(
        "SOFT-LIMIT EVENTS: "
        f"{rate.get('soft_limit_events', 0)}"
    )
    print(
        "SOFT-LIMIT RECOVERED: "
        f"{rate.get('soft_limit_recoveries', 0)}"
    )
    print(
        "FINAL RATE GAP:  "
        f"{rate.get('current_interval_seconds', 0)}s"
    )
    circuit_breaker = data.get("circuit_breaker", {})
    print(
        "CIRCUIT BREAKER: "
        f"{'OPEN' if circuit_breaker.get('opened') else 'CLOSED'}"
    )
    resume = data.get("resume", {})
    print(
        "RESUME START:    "
        f"{resume.get('start') if resume.get('available') else '-'}"
    )
    print(
        "EXPIRED BEFORE OUTPUT: "
        f"{data.get('expired_before_output', 0)}"
    )
    print(
        "============================================\n"
    )

    if resume.get("available"):
        print(
            "Resume available from LinkedIn start="
            f"{resume['start']} (page {resume['linkedin_page']})."
        )
        print(
            f"Resume command can use: --start {resume['start']}\n"
        )

    if data["search_status"] == "failed":
        return 2

    if data["search_status"] == "partial":
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
