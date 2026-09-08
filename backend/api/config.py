"""
Production configuration for SCOUTJOBS API.

All settings come from environment variables.
Never hardcode secrets.
"""

import os
from functools import lru_cache
from typing import Optional
from urllib.parse import urlsplit, urlunsplit


def normalize_database_url(url: str) -> str:
    """
    Normalize a PostgreSQL URL to use the psycopg3 driver.

    - "postgresql+psycopg://..." is left unchanged.
    - "postgresql://..." becomes "postgresql+psycopg://...".
    - "postgres://..." (legacy scheme, e.g. some providers) becomes "postgresql+psycopg://...".

    All other URL components (user, password, host, port, database, query
    string) are preserved exactly via urlsplit/urlunsplit -- only the scheme
    is rewritten.
    """
    if not url:
        return url
    parts = urlsplit(url)
    if parts.scheme == "postgresql+psycopg":
        return url
    if parts.scheme in ("postgresql", "postgres"):
        return urlunsplit(parts._replace(scheme="postgresql+psycopg"))
    return url


@lru_cache()
def get_settings():
    """Get production settings from environment."""
    return Settings()


class Settings:
    """Production settings loaded from environment variables."""

    # Application
    APP_NAME: str = "SCOUTJOBS API"
    APP_VERSION: str = "2.0.0"
    GIT_SHA: str = os.getenv("GIT_SHA", "unknown")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    WORKERS: int = int(os.getenv("WORKERS", "2"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Database
    DATABASE_URL: str = normalize_database_url(os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://scoutjobs:scoutjobs@postgres:5432/scoutjobs"
    ))
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    # Valkey/Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://valkey:6379/0")

    # CORS. CORS_EXTRA_ORIGINS is an optional, comma-separated list of
    # additional allowed origins on top of CORS_ORIGINS -- e.g. for
    # temporarily testing against a Quick Tunnel trycloudflare.com URL.
    # Never becomes "*"; blank entries from an empty/trailing comma are
    # dropped rather than allowing an empty-string origin.
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:8000").split(",")
    CORS_EXTRA_ORIGINS: list = [
        origin.strip() for origin in os.getenv("CORS_EXTRA_ORIGINS", "").split(",")
        if origin.strip() and origin.strip() != "*"
    ]

    # Rate limiting (per minute/IP) - environment configurable
    RATE_LIMIT_SEARCH_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_SEARCH_PER_MINUTE", "10"))
    RATE_LIMIT_POLL_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_POLL_PER_MINUTE", "60"))
    RATE_LIMIT_DETAIL_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_DETAIL_PER_MINUTE", "20"))

    # Cache TTLs (seconds)
    SEARCH_CACHE_TTL_SECONDS: int = int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "90"))
    DETAIL_CACHE_TTL_SECONDS: int = int(os.getenv("DETAIL_CACHE_TTL_SECONDS", "1800"))

    # Search limits
    MAX_JOBS: int = int(os.getenv("MAX_JOBS", "500"))
    MAX_PAGES: int = int(os.getenv("MAX_PAGES", "100"))

    # Worker
    LINKEDIN_JOB_TIMEOUT_SECONDS: int = int(os.getenv("LINKEDIN_JOB_TIMEOUT_SECONDS", "1200"))
    SEARCH_STALE_AFTER_SECONDS: int = int(os.getenv("SEARCH_STALE_AFTER_SECONDS", "1800"))
    WORKER_CONCURRENCY: int = 1  # LinkedIn: exactly ONE worker initially
    QUEUE_NAME: str = "linkedin_search"

    # Cloudflare Tunnel (production only)
    TRUST_CF_CONNECTING_IP: bool = os.getenv("TRUST_CF_CONNECTING_IP", "false").lower() == "true"

    # Request ID
    REQUEST_ID_HEADER: str = "X-Request-ID"
