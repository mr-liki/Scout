"""
Database models for SCOUTJOBS production persistence.

Uses SQLAlchemy 2 with async support.
Tables: searches, jobs, search_jobs, job_details
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Search(Base):
    """Search request and status tracking."""
    __tablename__ = "searches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Query parameters
    keywords: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=True)
    posted_within: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    under_10: Mapped[bool] = mapped_column(Boolean, default=False)
    easy_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_mode: Mapped[str] = mapped_column(String(20), default="newest")
    max_jobs: Mapped[int] = mapped_column(Integer, default=50)
    max_pages: Mapped[int] = mapped_column(Integer, default=20)
    start_offset: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False
    )  # queued, running, success, partial, failed
    search_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    stop_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zero_conclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Resume
    resume_available: Mapped[bool] = mapped_column(Boolean, default=False)
    resume_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resume_linkedin_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resume_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Circuit breaker
    circuit_breaker_opened: Mapped[bool] = mapped_column(Boolean, default=False)
    circuit_breaker_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    circuit_breaker_failed_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    circuit_breaker_failed_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Connector metadata
    connector_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    jobs: Mapped[list["SearchJob"]] = relationship(
        "SearchJob", back_populates="search", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_search_provider_hash", "provider", "query_hash"),
        Index("idx_search_status", "status"),
        Index("idx_search_created", "created_at"),
    )


class Job(Base):
    """Canonical job record with stable identity."""
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_job_id: Mapped[str] = mapped_column(String(200), nullable=False)
    
    # Canonical fields
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(500), nullable=True)
    location: Mapped[str] = mapped_column(String(500), nullable=True)
    link: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    posted_date: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    salary: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Flags
    easy_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    early_applicant: Mapped[bool] = mapped_column(Boolean, default=False)
    remote: Mapped[bool] = mapped_column(Boolean, default=False)

    # Provider metadata
    provider_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Detail fields
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applicants: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seniority_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_function: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industries: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Timestamps
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    detail_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("source", "provider_job_id", name="uq_job_source_provider_id"),
        Index("idx_job_source_provider", "source", "provider_job_id"),
        Index("idx_job_first_seen", "first_seen_at"),
    )


class SearchJob(Base):
    """Many-to-many: search results to jobs."""
    __tablename__ = "search_jobs"

    search_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("searches.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    search: Mapped["Search"] = relationship("Search", back_populates="jobs")
    job: Mapped["Job"] = relationship("Job")

    __table_args__ = (
        Index("idx_search_job_search", "search_id"),
        Index("idx_search_job_job", "job_id"),
    )


class JobDetail(Base):
    """Cached LinkedIn job details."""
    __tablename__ = "job_details"

    job_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_job_detail_fetched", "fetched_at"),
    )
