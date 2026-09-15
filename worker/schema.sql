-- SCOUTJOBS D1 Schema

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  company TEXT,
  location TEXT,
  link TEXT,
  posted_date TEXT,
  salary TEXT,
  description TEXT,
  experience TEXT,
  easy_apply INTEGER DEFAULT 0,
  early_applicant INTEGER DEFAULT 0,
  remote INTEGER DEFAULT 0,
  company_rating TEXT,
  applicants INTEGER,
  provider_metadata TEXT,
  first_seen_at TEXT DEFAULT (datetime('now')),
  last_seen_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_date);

CREATE TABLE IF NOT EXISTS searches (
  id TEXT PRIMARY KEY,
  keywords TEXT NOT NULL,
  location TEXT,
  query_hash TEXT NOT NULL,
  total INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_searches_hash ON searches(query_hash);

CREATE TABLE IF NOT EXISTS scrape_status (
  source TEXT PRIMARY KEY,
  last_run TEXT,
  last_success TEXT,
  jobs_count INTEGER DEFAULT 0,
  error TEXT
);
