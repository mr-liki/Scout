import type { Env, TrackerJob } from "../types";
import { fetchWithTimeout } from "../lib/fetch-timeout";

const API_URL = "https://www.foundit.in/middleware/jobsearch";
const JOBS_BASE = "https://www.foundit.in";

const HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json, text/plain, */*",
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  Origin: "https://www.foundit.in",
  Referer: "https://www.foundit.in/srp/results",
};

function cleanText(v: any): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s ? s : null;
}

function parseJob(raw: any): TrackerJob | null {
  // Skip ads
  if (raw.type || !raw.title) return null;

  const jobId = raw.jobId || raw.id;
  const title = cleanText(raw.title);
  if (!title) return null;

  const hideCompany = raw.hideCompanyName;
  const company = hideCompany ? null : cleanText(raw.companyName);

  // Salary
  let salary = cleanText(raw.salary);
  if (raw.hideSalary || (salary && salary.includes("0-0"))) salary = null;

  // Link
  let link: string | null = null;
  if (raw.seoJdUrl) link = `${JOBS_BASE}${raw.seoJdUrl}`;
  else if (raw.redirectUrl) link = raw.redirectUrl;

  // Posted date from epoch ms
  let postedDate: string | null = null;
  const created = raw.createdAt || raw.freshness;
  if (created && typeof created === "number") {
    try {
      postedDate = new Date(created).toISOString().slice(0, 10);
    } catch {}
  }

  return {
    source: "foundit",
    title,
    company,
    location: cleanText(raw.locations),
    link,
    posted_date: postedDate,
    salary,
    experience: cleanText(raw.exp),
  };
}

// Foundit's `locations` param wants a bare city name ("bengaluru") — the
// full "City, State, Country" string the frontend sends silently fails to
// filter at all (confirmed directly: passing the full string returned jobs
// scattered across Chennai/Pune/Mumbai/etc for a Bengaluru search, while
// passing just "bengaluru" correctly filtered to Bengaluru-only results).
function extractCity(location: string): string {
  return location.split(",")[0].trim();
}

function buildFounditUrl(keywords: string, location: string): string {
  const params = new URLSearchParams({
    query: keywords,
    start: "0",
    limit: "25",
    sort: "",
  });
  if (location) params.set("locations", extractCity(location));
  return `${API_URL}?${params}`;
}

function extractJobs(data: any): TrackerJob[] {
  const items = data?.jobSearchResponse?.data || [];
  const jobs: TrackerJob[] = [];
  for (const item of items) {
    const job = parseJob(item);
    if (job) jobs.push(job);
  }
  return jobs;
}

// The 403 here is Akamai (not Cloudflare, and not Foundit-application-level)
// — confirmed by reading the actual response: `akamai-grn` header, body
// pointing at errors.edgesuite.net (Akamai's own error-page domain), "Access
// Denied". Akamai's IP-reputation layer evidently flags Cloudflare's network
// ranges as known hosting/proxy space at the ASN level, not per-product —
// confirmed by retrying via Browser Rendering (a different Cloudflare
// product, different egress) after fixing the concurrency-sharing issue
// with LinkedIn (lib/shared-browser.ts): that fix worked cleanly (both got
// sessions in the same request, no contention), but Foundit still 403'd
// 4/4 times. So this doesn't have a Cloudflare-native fix — any egress IP
// from Cloudflare's network hits the same Akamai wall regardless of which
// Cloudflare product originates it.
//
// Tested directly against ScraperAPI: its basic (free-tier) proxy pool
// fails against Foundit the same way — "Protected domains may require
// adding premium=true OR ultra_premium=true" — and ultra_premium itself is
// rejected outright on the free plan ("upgrade your plan to gain access").
// So Foundit specifically needs a residential-class IP, not just any
// non-Cloudflare one; ScraperAPI's free tier can't provide that. Kept as a
// fallback for if the plan is ever upgraded, but tried with a short
// timeout since on the free tier it's known to always fail (and takes
// 40+ seconds to fail on ScraperAPI's own end if given the chance).
async function searchFounditViaScraperApi(
  keywords: string,
  location: string,
  apiKey: string
): Promise<TrackerJob[]> {
  const targetUrl = buildFounditUrl(keywords, location);
  const proxyUrl = `https://api.scraperapi.com/?api_key=${encodeURIComponent(apiKey)}&url=${encodeURIComponent(targetUrl)}`;

  const resp = await fetchWithTimeout(proxyUrl, {}, 6000);
  if (!resp.ok) throw new Error(`Foundit ScraperAPI HTTP ${resp.status}`);

  const data = await resp.json();
  return extractJobs(data);
}

// A small self-hosted proxy (local-proxy/deno-deploy.ts or server.js) that
// forwards this exact request from a non-Cloudflare, non-datacenter IP.
// Untested whether any given host's IP range actually dodges Akamai's
// check — that's what deploying and setting this secret verifies.
async function searchFounditViaOwnProxy(
  keywords: string,
  location: string,
  proxyUrl: string,
  proxyKey: string
): Promise<TrackerJob[]> {
  const params = new URLSearchParams({ query: keywords, limit: "25" });
  if (location) params.set("location", extractCity(location));

  const resp = await fetchWithTimeout(`${proxyUrl.replace(/\/$/, "")}/foundit?${params}`, {
    headers: { "x-proxy-key": proxyKey },
  }, 12000);
  if (!resp.ok) throw new Error(`Foundit own-proxy HTTP ${resp.status}`);

  const data = await resp.json();
  return extractJobs(data);
}

export async function searchFoundit(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  if (env.FOUNDIT_PROXY_URL && env.FOUNDIT_PROXY_KEY) {
    try {
      const jobs = await searchFounditViaOwnProxy(keywords, location, env.FOUNDIT_PROXY_URL, env.FOUNDIT_PROXY_KEY);
      console.log(`[Foundit] Own proxy returned ${jobs.length} jobs`);
      return jobs;
    } catch (e: any) {
      console.warn(`[Foundit] Own proxy failed: ${e.message}, trying next option`);
    }
  }

  if (env.SCRAPERAPI_KEY) {
    try {
      const jobs = await searchFounditViaScraperApi(keywords, location, env.SCRAPERAPI_KEY);
      console.log(`[Foundit] ScraperAPI returned ${jobs.length} jobs`);
      return jobs;
    } catch (e: any) {
      console.warn(`[Foundit] ScraperAPI failed: ${e.message}, falling back to direct fetch`);
    }
  }

  const resp = await fetchWithTimeout(buildFounditUrl(keywords, location), {
    headers: HEADERS,
    cf: { cacheTtl: 60 },
  });
  if (!resp.ok) throw new Error(`Foundit HTTP ${resp.status}`);

  const data = await resp.json();
  return extractJobs(data);
}
