"""Initial database schema for SCOUTJOBS production.

Revision ID: 001_initial
Revises: None
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Searches table
    op.create_table(
        "searches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False, index=True),
        sa.Column("query_hash", sa.String(64), nullable=False, index=True),
        sa.Column("keywords", sa.String(500), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("posted_within", sa.String(20), nullable=True),
        sa.Column("under_10", sa.Boolean(), default=False),
        sa.Column("easy_apply", sa.Boolean(), default=False),
        sa.Column("sort_mode", sa.String(20), default="newest"),
        sa.Column("max_jobs", sa.Integer(), default=50),
        sa.Column("max_pages", sa.Integer(), default=20),
        sa.Column("start_offset", sa.Integer(), default=0),
        sa.Column("status", sa.String(20), default="queued", nullable=False),
        sa.Column("search_complete", sa.Boolean(), default=False),
        sa.Column("stop_reason", sa.String(50), nullable=True),
        sa.Column("zero_conclusive", sa.Boolean(), default=False),
        sa.Column("resume_available", sa.Boolean(), default=False),
        sa.Column("resume_start", sa.Integer(), nullable=True),
        sa.Column("resume_linkedin_page", sa.Integer(), nullable=True),
        sa.Column("resume_reason", sa.String(50), nullable=True),
        sa.Column("circuit_breaker_opened", sa.Boolean(), default=False),
        sa.Column("circuit_breaker_reason", sa.String(50), nullable=True),
        sa.Column("circuit_breaker_failed_start", sa.Integer(), nullable=True),
        sa.Column("circuit_breaker_failed_page", sa.Integer(), nullable=True),
        sa.Column("connector_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_search_provider_hash", "searches", ["provider", "query_hash"])
    op.create_index("idx_search_status", "searches", ["status"])
    op.create_index("idx_search_created", "searches", ["created_at"])

    # Jobs table
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("provider_job_id", sa.String(200), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(500), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("link", sa.String(2000), nullable=True),
        sa.Column("posted_date", sa.String(100), nullable=True),
        sa.Column("salary", sa.String(200), nullable=True),
        sa.Column("easy_apply", sa.Boolean(), default=False),
        sa.Column("early_applicant", sa.Boolean(), default=False),
        sa.Column("remote", sa.Boolean(), default=False),
        sa.Column("provider_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("applicants", sa.String(200), nullable=True),
        sa.Column("seniority_level", sa.String(100), nullable=True),
        sa.Column("employment_type", sa.String(100), nullable=True),
        sa.Column("job_function", sa.String(100), nullable=True),
        sa.Column("industries", sa.String(200), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("detail_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source", "provider_job_id", name="uq_job_source_provider_id"),
    )
    op.create_index("idx_job_source_provider", "jobs", ["source", "provider_job_id"])
    op.create_index("idx_job_first_seen", "jobs", ["first_seen_at"])

    # Search-Jobs junction table
    op.create_table(
        "search_jobs",
        sa.Column("search_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("searches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_search_job_search", "search_jobs", ["search_id"])
    op.create_index("idx_search_job_job", "search_jobs", ["job_id"])

    # Job Details cache
    op.create_table(
        "job_details",
        sa.Column("job_id", sa.String(200), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_job_detail_fetched", "job_details", ["fetched_at"])


def downgrade() -> None:
    op.drop_table("job_details")
    op.drop_table("search_jobs")
    op.drop_table("jobs")
    op.drop_table("searches")
