export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  AI: Ai;
  BROWSER: Fetcher;
  ALLOWED_ORIGINS: string;
  EMAIL_WEBHOOK_URL?: string;
  NOTIFY_TO_EMAIL?: string;
  // Optional: RapidAPI key for the "linkedin-data-api" service. When set,
  // LinkedIn searches route through it instead of scraping LinkedIn
  // directly — see trackers/linkedin-rss.ts for why.
  RAPID_API_KEY?: string;
  // Optional: ScraperAPI key (scraperapi.com). When set, Foundit searches
  // try routing through it to get past an Akamai IP-reputation block on
  // Cloudflare's network — see trackers/foundit.ts. In practice this only
  // helps on a paid ScraperAPI plan; their free-tier proxy pool is also
  // datacenter-class and hits the same block.
  SCRAPERAPI_KEY?: string;
  // Optional: URL + shared key for a small self-hosted proxy (see
  // local-proxy/) that forwards Foundit requests from a non-Cloudflare,
  // non-datacenter IP — see trackers/foundit.ts.
  FOUNDIT_PROXY_URL?: string;
  FOUNDIT_PROXY_KEY?: string;
  // Optional: URL + shared key for glassdoor-proxy/ (a real Python service
  // on Render.com using curl_cffi's Chrome TLS impersonation — Glassdoor's
  // block is a TLS fingerprint check, not IP-based, so this needs a real
  // TLS stack, not just a different network origin). See trackers/glassdoor.ts.
  // _2/_3 are the same code deployed to additional Render regions (same
  // PROXY_KEY, different outbound IP pool) — tried in order as a fallback
  // against one region's shared IP being temporarily rate-limited.
  GLASSDOOR_PROXY_URL?: string;
  GLASSDOOR_PROXY_URL_2?: string;
  GLASSDOOR_PROXY_URL_3?: string;
  GLASSDOOR_PROXY_KEY?: string;
  // Not a real Cloudflare binding — injected per-request by
  // searchAllTrackers (trackers/index.ts) so trackers that need Browser
  // Rendering (currently just LinkedIn) can share one browser session
  // instead of each launching their own and competing for the account's
  // single concurrency slot. See lib/shared-browser.ts.
  getSharedBrowser?: () => Promise<import("@cloudflare/puppeteer").Browser>;
}

export interface Job {
  id: string;
  source: string;
  title: string;
  company: string | null;
  location: string | null;
  link: string | null;
  posted_date: string | null;
  salary: string | null;
  description: string | null;
  experience: string | null;
  easy_apply: number;
  early_applicant: number;
  remote: number;
  company_rating: string | null;
  applicants: number | null;
  provider_metadata: string | null;
  first_seen_at: string;
  last_seen_at: string;
}

export interface TrackerJob {
  source: string;
  title: string;
  company: string | null;
  location: string | null;
  link: string | null;
  posted_date: string | null;
  salary: string | null;
  description?: string | null;
  experience?: string | null;
  easy_apply?: boolean;
  early_applicant?: boolean;
  remote?: boolean;
  company_rating?: string | null;
  applicants?: number | null;
}

export interface ScrapeStatus {
  source: string;
  last_run: string | null;
  last_success: string | null;
  jobs_count: number;
  error: string | null;
}

export type TrackerFn = (
  keywords: string,
  location: string,
  env: Env
) => Promise<TrackerJob[]>;
