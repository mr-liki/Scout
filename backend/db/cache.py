"""
Valkey/Redis caching layer for SCOUTJOBS production.

Caches: search results, job details, query locks, rate limiting counters.
Supports freshness-safe cache aging.
"""

import json
import hashlib
import time
import logging
from typing import Any, Optional

import redis

from backend.api.config import get_settings

logger = logging.getLogger("scoutjobs.cache")


class CacheManager:
    """Redis/Valkey cache manager with graceful degradation."""

    def __init__(self):
        settings = get_settings()
        try:
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self._available = True
        except Exception as e:
            logger.warning("Valkey unavailable, operating in degraded mode: %s", e)
            self.redis = None
            self._available = False
        self.settings = settings

    @property
    def available(self) -> bool:
        """Check if cache is available."""
        return self._available and self.redis is not None

    def close(self):
        """Close Redis connection."""
        if self.redis:
            try:
                self.redis.close()
            except Exception:
                pass

    # ---- Query Hash ----

    @staticmethod
    def generate_query_hash(
        keywords: str,
        location: str = "",
        posted_within: str = None,
        under_10: bool = False,
        easy_apply: bool = False,
        sort_mode: str = "newest",
        limit: int = 50,
        max_pages: int = 20,
    ) -> str:
        """Generate deterministic SHA-256 hash for search query dedup."""
        normalized = {
            "keywords": keywords.lower().strip(),
            "location": location.lower().strip(),
            "posted_within": posted_within,
            "under_10": under_10,
            "easy_apply": easy_apply,
            "sort_mode": sort_mode,
            "limit": limit,
            "max_pages": max_pages,
        }
        raw = json.dumps(normalized, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    # ---- Search Cache ----

    def cache_search_result(self, query_hash: str, data: dict, ttl: int = None) -> None:
        """Cache search result with TTL."""
        if not self.available:
            return
        try:
            if ttl is None:
                ttl = self.settings.SEARCH_CACHE_TTL_SECONDS
            key = f"search:{query_hash}"
            self.redis.setex(key, ttl, json.dumps(data))
        except Exception as e:
            logger.warning("Cache write failed: %s", e)

    def get_cached_search(self, query_hash: str) -> Optional[dict]:
        """Get cached search result if exists."""
        if not self.available:
            return None
        try:
            key = f"search:{query_hash}"
            data = self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("Cache read failed: %s", e)
            return None

    # ---- Job Detail Cache ----

    def cache_job_detail(self, job_id: str, data: dict, ttl: int = None) -> None:
        """Cache job detail with TTL. Never cache challenge pages."""
        if not self.available:
            return
        try:
            # Don't cache challenge/interstitial pages
            if data.get("upstream_status") in ("rate_limited", "unavailable", "error"):
                return
            if ttl is None:
                ttl = self.settings.DETAIL_CACHE_TTL_SECONDS
            key = f"linkedin:detail:{job_id}"
            self.redis.setex(key, ttl, json.dumps(data))
        except Exception as e:
            logger.warning("Detail cache write failed: %s", e)

    def get_cached_job_detail(self, job_id: str) -> Optional[dict]:
        """Get cached job detail if exists."""
        if not self.available:
            return None
        try:
            key = f"linkedin:detail:{job_id}"
            data = self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("Detail cache read failed: %s", e)
            return None

    # ---- Query Locks ----

    def acquire_search_lock(self, query_hash: str, ttl: int = 60) -> bool:
        """Try to acquire lock for a search query."""
        if not self.available:
            return True  # Proceed without lock if cache unavailable
        try:
            key = f"lock:search:{query_hash}"
            return self.redis.set(key, "1", nx=True, ex=ttl)
        except Exception as e:
            logger.warning("Lock acquire failed: %s", e)
            return True

    def release_search_lock(self, query_hash: str) -> None:
        """Release search lock."""
        if not self.available:
            return
        try:
            key = f"lock:search:{query_hash}"
            self.redis.delete(key)
        except Exception as e:
            logger.warning("Lock release failed: %s", e)

    def is_search_running(self, query_hash: str) -> bool:
        """Check if a search is currently running."""
        if not self.available:
            return False
        try:
            key = f"lock:search:{query_hash}"
            return bool(self.redis.exists(key))
        except Exception as e:
            logger.warning("Lock check failed: %s", e)
            return False

    # ---- Rate Limiting ----

    def check_rate_limit(self, identifier: str, limit: int, window: int = 60) -> bool:
        """Check if rate limit is exceeded using sliding window."""
        if not self.available:
            return True  # Allow if cache unavailable
        try:
            key = f"ratelimit:{identifier}"
            now = time.time()
            window_start = now - window

            # Remove old entries
            self.redis.zremrangebyscore(key, 0, window_start)

            # Count current window
            count = self.redis.zcard(key)

            if count >= limit:
                return False

            # Add current request
            self.redis.zadd(key, {str(now): now})
            self.redis.expire(key, window)

            return True
        except Exception as e:
            logger.warning("Rate limit check failed: %s", e)
            return True  # Allow if cache unavailable

    def get_rate_limit_remaining(self, identifier: str, limit: int, window: int = 60) -> int:
        """Get remaining rate limit count."""
        if not self.available:
            return limit
        try:
            key = f"ratelimit:{identifier}"
            now = time.time()
            window_start = now - window

            self.redis.zremrangebyscore(key, 0, window_start)
            count = self.redis.zcard(key)

            return max(0, limit - count)
        except Exception:
            return limit
