"""
SCOUTJOBS FastAPI Production Application.

Routes:
    POST /api/v1/searches - Create search
    GET /api/v1/searches/{search_id} - Get search status
    POST /api/v1/searches/{search_id}/resume - Resume search
    GET /api/jobs/linkedin/{job_id} - Lazy detail
    GET /healthz - Health check
    GET /readyz - Readiness check
"""

import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.config import get_settings
from db.session import get_session, get_async_engine
from db.models import Search, Job, SearchJob, JobDetail
from db.cache import CacheManager

logger = logging.getLogger("scoutjobs.api")


# ---- Pydantic Models ----

class SearchCreateRequest(BaseModel):
    """Request model for creating a search."""
    keywords: str = Field(..., min_length=1, max_length=500)
    location: str = Field(default="", max_length=500)
    posted_within: Optional[str] = Field(default=None, max_length=20)
    under_10: bool = Field(default=False)
    easy_apply: bool = Field(default=False)
    sort_mode: str = Field(default="newest", pattern="^(newest|relevance)$")
    limit: int = Field(default=50, ge=1, le=500)
    max_pages: int = Field(default=20, ge=1, le=100)
    start: int = Field(default=0, ge=0)


class SearchResponse(BaseModel):
    """Response model for search status."""
    search_id: str
    status: str
    search_complete: bool
    stop_reason: Optional[str] = None
    zero_conclusive: bool
    resume: Optional[dict] = None
    circuit_breaker: Optional[dict] = None
    jobs: list = []
    total_jobs: int = 0
    error: Optional[str] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None


# ---- App Setup ----

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS - exact origins only, never a wildcard. CORS_EXTRA_ORIGINS lets
# operators temporarily allow a Quick Tunnel trycloudflare.com URL alongside
# the real production origin (see docs/QUICK_TUNNEL_TESTING.md).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS + settings.CORS_EXTRA_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Redis/Valkey connection
redis_client = None
cache_manager = None


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID middleware."""
    request_id = request.headers.get(settings.REQUEST_ID_HEADER) or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[settings.REQUEST_ID_HEADER] = request_id
    return response


@app.on_event("startup")
async def startup():
    global redis_client, cache_manager
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    cache_manager = CacheManager()
    logger.info(
        "SCOUTJOBS API started: version=%s git_sha=%s environment=%s",
        settings.APP_VERSION, settings.GIT_SHA, settings.ENVIRONMENT
    )


@app.on_event("shutdown")
async def shutdown():
    global redis_client, cache_manager
    if cache_manager:
        cache_manager.close()
    if redis_client:
        redis_client.close()
    logger.info("SCOUTJOBS API stopped")


# ---- Rate Limiting ----

def get_client_ip(request: Request) -> str:
    """Get client IP, respecting Cloudflare header in production."""
    if settings.TRUST_CF_CONNECTING_IP:
        return request.headers.get("CF-Connecting-IP", request.client.host)
    return request.client.host


def check_rate_limit(request: Request, limit_type: str = "search"):
    """Check rate limit for client."""
    client_ip = get_client_ip(request)

    if limit_type == "search":
        limit = settings.RATE_LIMIT_SEARCH_PER_MINUTE
    elif limit_type == "poll":
        limit = settings.RATE_LIMIT_POLL_PER_MINUTE
    elif limit_type == "detail":
        limit = settings.RATE_LIMIT_DETAIL_PER_MINUTE
    else:
        limit = 60

    identifier = f"{limit_type}:{client_ip}"
    if not cache_manager.check_rate_limit(identifier, limit):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


# ---- Helper Functions ----

def generate_query_hash(request: SearchCreateRequest) -> str:
    """Generate deterministic query hash."""
    return CacheManager.generate_query_hash(
        keywords=request.keywords,
        location=request.location,
        posted_within=request.posted_within,
        under_10=request.under_10,
        easy_apply=request.easy_apply,
        sort_mode=request.sort_mode,
        limit=request.limit,
        max_pages=request.max_pages,
    )


# ---- Routes ----

@app.post("/api/v1/searches", response_model=SearchResponse)
async def create_search(
    request: Request,
    body: SearchCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a new LinkedIn search (async background job)."""
    check_rate_limit(request, "search")

    query_hash = generate_query_hash(body)

    # Check for running search with same query
    result = await session.execute(
        Search.__table__.select().where(
            Search.query_hash == query_hash,
            Search.status.in_(["queued", "running"]),
        )
    )
    existing_search = result.first()
    if existing_search:
        return SearchResponse(
            search_id=str(existing_search.id),
            status=existing_search.status,
            search_complete=existing_search.search_complete,
            stop_reason=existing_search.stop_reason,
            zero_conclusive=existing_search.zero_conclusive,
        )

    # Check for recent completed result in cache
    cached = cache_manager.get_cached_search(query_hash)
    if cached and cached.get("search_id"):
        # Verify search still exists in DB
        db_check = await session.execute(
            Search.__table__.select().where(Search.id == cached["search_id"])
        )
        db_search = db_check.first()
        if db_search:
            return SearchResponse(
                search_id=str(db_search.id),
                status=db_search.status,
                search_complete=db_search.search_complete,
                stop_reason=db_search.stop_reason,
                zero_conclusive=db_search.zero_conclusive,
            )

    # Create search record
    search = Search(
        provider="linkedin",
        query_hash=query_hash,
        keywords=body.keywords,
        location=body.location,
        posted_within=body.posted_within,
        under_10=body.under_10,
        easy_apply=body.easy_apply,
        sort_mode=body.sort_mode,
        max_jobs=body.limit,
        max_pages=body.max_pages,
        start_offset=body.start,
        status="queued",
    )
    session.add(search)
    await session.flush()
    # Commit before enqueueing -- the worker uses a separate DB connection
    # and can start executing the job before it exists, and needs the row
    # to actually be durable, not just visible inside this transaction.
    await session.commit()

    search_id = str(search.id)

    # Enqueue background job (using RQ with proper timeout)
    try:
        from redis import Redis
        from rq import Queue

        q = Queue(settings.QUEUE_NAME, connection=redis_client)
        job = q.enqueue(
            "backend.worker.linkedin_worker.run_linkedin_search",
            search_id,
            job_timeout=settings.LINKEDIN_JOB_TIMEOUT_SECONDS,
        )
        logger.info("Enqueued search %s with timeout %ds", search_id, settings.LINKEDIN_JOB_TIMEOUT_SECONDS)
    except Exception as e:
        logger.error("Failed to enqueue search %s: %s", search_id, e)
        search.status = "failed"
        search.error_message = f"Queue error: {e}"
        await session.commit()
        raise HTTPException(status_code=503, detail="Search queue unavailable")

    return SearchResponse(
        search_id=search_id,
        status="queued",
        search_complete=False,
        zero_conclusive=False,
        created_at=search.created_at.isoformat() if search.created_at else None,
    )


@app.get("/api/v1/searches/{search_id}", response_model=SearchResponse)
async def get_search(
    request: Request,
    search_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get search status and results."""
    check_rate_limit(request, "poll")

    # Validate UUID
    try:
        uuid.UUID(search_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid search ID")

    result = await session.execute(
        Search.__table__.select().where(Search.id == search_id)
    )
    search = result.first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    # Load jobs
    jobs_result = await session.execute(
        SearchJob.__table__.select().where(SearchJob.search_id == search_id)
    )
    search_jobs = jobs_result.fetchall()

    jobs = []
    for sj in search_jobs:
        job_result = await session.execute(
            Job.__table__.select().where(Job.id == sj.job_id)
        )
        job = job_result.first()
        if job:
            jobs.append({
                "id": str(job.id),
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "link": job.link,
                "posted_date": job.posted_date,
                "source": job.source,
                "easy_apply": job.easy_apply,
                "early_applicant": job.early_applicant,
                "remote": job.remote,
                "provider_metadata": job.provider_metadata,
            })

    return SearchResponse(
        search_id=str(search.id),
        status=search.status,
        search_complete=search.search_complete,
        stop_reason=search.stop_reason,
        zero_conclusive=search.zero_conclusive,
        resume={
            "available": search.resume_available,
            "start": search.resume_start,
            "linkedin_page": search.resume_linkedin_page,
            "reason": search.resume_reason,
        } if search.resume_available else None,
        circuit_breaker={
            "opened": search.circuit_breaker_opened,
            "reason": search.circuit_breaker_reason,
            "failed_start": search.circuit_breaker_failed_start,
            "failed_page": search.circuit_breaker_failed_page,
        } if search.circuit_breaker_opened else None,
        jobs=jobs,
        total_jobs=len(jobs),
        error=search.error_message,
        created_at=search.created_at.isoformat() if search.created_at else None,
        finished_at=search.finished_at.isoformat() if search.finished_at else None,
    )


@app.post("/api/v1/searches/{search_id}/resume", response_model=SearchResponse)
async def resume_search(
    request: Request,
    search_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Resume a paused/failed search from exact resume.start."""
    check_rate_limit(request, "search")

    try:
        uuid.UUID(search_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid search ID")

    result = await session.execute(
        Search.__table__.select().where(Search.id == search_id)
    )
    search = result.first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    if not search.resume_available:
        raise HTTPException(status_code=400, detail="Resume not available for this search")

    # Create new search with same params but new start offset
    new_search = Search(
        provider="linkedin",
        query_hash=search.query_hash,
        keywords=search.keywords,
        location=search.location,
        posted_within=search.posted_within,
        under_10=search.under_10,
        easy_apply=search.easy_apply,
        sort_mode=search.sort_mode,
        max_jobs=search.max_jobs,
        max_pages=search.max_pages,
        start_offset=search.resume_start,
        status="queued",
    )
    session.add(new_search)
    await session.flush()
    # Commit before enqueueing -- see create_search() for why.
    await session.commit()

    # Enqueue
    try:
        from redis import Redis
        from rq import Queue

        q = Queue(settings.QUEUE_NAME, connection=redis_client)
        q.enqueue(
            "backend.worker.linkedin_worker.run_linkedin_search",
            str(new_search.id),
            job_timeout=settings.LINKEDIN_JOB_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.error("Failed to enqueue resume: %s", e)
        new_search.status = "failed"
        new_search.error_message = f"Queue error: {e}"
        await session.commit()
        raise HTTPException(status_code=503, detail="Search queue unavailable")

    return SearchResponse(
        search_id=str(new_search.id),
        status="queued",
        search_complete=False,
        zero_conclusive=False,
    )


@app.get("/api/jobs/linkedin/{job_id}")
async def get_linkedin_detail(
    request: Request,
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Lazy detail fetch for a single LinkedIn job."""
    check_rate_limit(request, "detail")

    if not job_id or not re.match(r"^\d+$", job_id):
        raise HTTPException(status_code=400, detail="Invalid LinkedIn job ID")

    # Check Valkey cache first
    cached = cache_manager.get_cached_job_detail(job_id)
    if cached:
        return cached

    # Check database cache
    result = await session.execute(
        JobDetail.__table__.select().where(JobDetail.job_id == job_id)
    )
    db_detail = result.first()
    if db_detail:
        # Re-cache in Valkey
        cache_manager.cache_job_detail(job_id, db_detail.data)
        return db_detail.data

    # Fetch from LinkedIn
    from worker.linkedin_service import fetch_linkedin_job_detail
    detail = fetch_linkedin_job_detail(job_id, cache=cache_manager)

    # Store in database if successful
    if detail.get("upstream_status") == "success":
        job_detail = JobDetail(
            job_id=job_id,
            source="linkedin",
            data=detail,
        )
        session.add(job_detail)
        await session.flush()

    status_code = 200
    if detail.get("upstream_status") == "rate_limited":
        status_code = 429
    elif detail.get("upstream_status") in ("unavailable", "error"):
        status_code = 502
    elif detail.get("upstream_status") == "invalid_id":
        status_code = 400

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=detail)

    return detail


@app.get("/healthz")
async def healthz():
    """Health check - does not contact external services."""
    return {
        "status": "ok",
        "service": "SCOUTJOBS API",
        "version": settings.APP_VERSION,
        "git_sha": settings.GIT_SHA,
    }


@app.get("/readyz")
async def readyz():
    """Readiness check - verifies PostgreSQL and Valkey connectivity."""
    checks = {"postgres": False, "valkey": False}

    # Check PostgreSQL
    try:
        async with get_async_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
            checks["postgres"] = True
    except Exception as e:
        logger.warning("PostgreSQL readiness check failed: %s", e)

    # Check Valkey
    try:
        if redis_client:
            redis_client.ping()
            checks["valkey"] = True
    except Exception as e:
        logger.warning("Valkey readiness check failed: %s", e)

    all_ok = all(checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "database": "ok" if checks["postgres"] else "unavailable",
        "cache": "ok" if checks["valkey"] else "unavailable",
    }
