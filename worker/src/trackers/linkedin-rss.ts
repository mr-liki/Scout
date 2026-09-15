import puppeteer from "@cloudflare/puppeteer";
import type { Env, TrackerJob } from "../types";

const SEARCH_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search";
const RSS_SEARCH_URL = "https://www.linkedin.com/jobs/search";
const JOBS_BASE = "https://www.linkedin.com/jobs/view/";
const RAPIDAPI_URL = "https://linkedin-data-api.p.rapidapi.com/search-jobs";

const UA_POOL = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:133.0) Gecko/20100101 Firefox/133.0",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
];

const LINKEDIN_COOKIES = [
  "li_sugr=abc123def456",
  "bcookie=v=2&fake-id-1",
  "lidc=\"b=VB80:s=V:r=V:a=V:p=V:sl=1\"",
];

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function cleanText(v: any): string | null {
  if (v == null) return null;
  const s = String(v).replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").trim();
  return s ? s : null;
}

function buildHeaders(endpoint: "api" | "html" = "api"): Record<string, string> {
  const ua = pick(UA_POOL);
  const isFirefox = ua.includes("Firefox");
  const isSafari = ua.includes("Safari") && !ua.includes("Chrome");

  const headers: Record<string, string> = {
    "User-Agent": ua,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": `max-age=0, no-cache`,
    "Pragma": "no-cache",
  };

  if (endpoint === "api") {
    headers["Referer"] = "https://www.linkedin.com/jobs/search/?keywords=developer&location=United%20States";
    headers["Sec-Fetch-Dest"] = "empty";
    headers["Sec-Fetch-Mode"] = "cors";
    headers["Sec-Fetch-Site"] = "same-origin";
    headers["X-Requested-With"] = "XMLHttpRequest";
  } else {
    headers["Referer"] = "https://www.linkedin.com/feed/";
    headers["Sec-Fetch-Dest"] = "document";
    headers["Sec-Fetch-Mode"] = "navigate";
    headers["Sec-Fetch-Site"] = "same-origin";
    headers["Sec-Fetch-User"] = "?1";
  }

  if (isFirefox) {
    headers["Sec-Fetch-Dest"] = endpoint === "api" ? "" : "document";
  }
  if (isSafari) {
    delete headers["Sec-Fetch-Dest"];
    delete headers["Sec-Fetch-Mode"];
    delete headers["Sec-Fetch-Site"];
    delete headers["Sec-Fetch-User"];
  }

  headers["Cookie"] = pick(LINKEDIN_COOKIES);

  return headers;
}

const FETCH_TIMEOUT_MS = 6000;

async function fetchWithTimeout(url: string, headers: Record<string, string>): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(url, { headers, redirect: "follow", signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function fetchLinkedIn(url: string, endpoint: "api" | "html" = "api"): Promise<string> {
  // Only 2 attempts, and no wait after the final one — a failed last attempt
  // should throw immediately rather than sleep for nothing. LinkedIn's 429/403
  // here reflects Cloudflare Workers' shared egress IP reputation, not a
  // per-request cooldown, so a short wait is just as effective as a long one.
  const maxRetries = 2;
  let lastErr: Error | null = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const res = await fetchWithTimeout(url, buildHeaders(endpoint));

      if (res.status === 429 || res.status === 403) {
        lastErr = new Error(`LinkedIn HTTP ${res.status}`);
        console.warn(`[LinkedIn] ${res.status} on attempt ${attempt}`);
        if (attempt < maxRetries) {
          await sleep(res.status === 429 ? 1500 : 2000);
        }
        continue;
      }

      if (res.status === 302 || res.status === 301) {
        throw new Error(`LinkedIn redirect ${res.status}`);
      }

      if (res.status === 200) {
        return res.text();
      }

      throw new Error(`LinkedIn HTTP ${res.status}`);
    } catch (err: any) {
      lastErr = err?.name === "AbortError" ? new Error("LinkedIn fetch timed out") : err;
      if (attempt < maxRetries) {
        await sleep(1000);
      }
    }
  }

  throw lastErr || new Error("LinkedIn fetch failed after retries");
}

function parseHtmlCards(html: string, seenLinks: Set<string>): TrackerJob[] {
  const jobs: TrackerJob[] = [];
  const cardRegex = /<li[\s\S]*?<\/li>/g;
  let match: RegExpExecArray | null;

  while ((match = cardRegex.exec(html)) !== null) {
    const cardHtml = match[0];

    const titleMatch = cardHtml.match(
      /class="[^"]*base-search-card__title[^"]*"[^>]*>([\s\S]*?)<\/h3>/
    );
    const title = cleanText(titleMatch?.[1]);
    if (!title) continue;

    const companyMatch = cardHtml.match(
      /class="[^"]*base-search-card__subtitle[^"]*"[^>]*>([\s\S]*?)<\/h4/
    );
    const company = cleanText(
      companyMatch?.[1]?.replace(/<[^>]+>/g, "")
    );

    const locationMatch = cardHtml.match(
      /class="[^"]*job-search-card__location[^"]*"[^>]*>([^<]+)/
    );
    const loc = cleanText(locationMatch?.[1]);

    const linkMatch = cardHtml.match(
      /href="(https:\/\/www\.linkedin\.com\/jobs\/view\/[^"?]+)/
    );
    const link = linkMatch?.[1] || null;

    if (link && seenLinks.has(link)) continue;
    if (link) seenLinks.add(link);

    let postedDate: string | null = null;
    const timeMatch = cardHtml.match(/datetime="([^"]+)"/);
    if (timeMatch?.[1]) {
      try {
        postedDate = new Date(timeMatch[1]).toISOString().slice(0, 10);
      } catch {}
    }

    const earlyApplicant = cardHtml.includes("semantic-search-premium");

    jobs.push({
      source: "linkedin",
      title,
      company,
      location: loc,
      link,
      posted_date: postedDate,
      early_applicant: earlyApplicant,
    });
  }

  return jobs;
}

function parseRssResults(xml: string, seenLinks: Set<string>): TrackerJob[] {
  const jobs: TrackerJob[] = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  let match: RegExpExecArray | null;

  while ((match = itemRegex.exec(xml)) !== null) {
    const item = match[1];

    const titleMatch = item.match(/<title>([\s\S]*?)<\/title>/);
    const title = cleanText(titleMatch?.[1]);
    if (!title) continue;

    const linkMatch = item.match(/<link>([\s\S]*?)<\/link>/);
    const link = cleanText(linkMatch?.[1]);
    if (link && seenLinks.has(link)) continue;
    if (link) seenLinks.add(link);

    const descMatch = item.match(/<description>([\s\S]*?)<\/description>/);
    const desc = cleanText(descMatch?.[1]) || "";

    const companyMatch = desc.match(/<h4[^>]*>([\s\S]*?)<\/h4>/);
    const company = cleanText(companyMatch?.[1]?.replace(/<[^>]+>/g, ""));

    const locationMatch = desc.match(/class="[^"]*job-search-card__location[^"]*"[^>]*>([^<]+)/);
    const loc = cleanText(locationMatch?.[1]);

    const timeMatch = item.match(/<pubDate>([^<]+)<\/pubDate>/);
    let postedDate: string | null = null;
    if (timeMatch?.[1]) {
      try {
        postedDate = new Date(timeMatch[1]).toISOString().slice(0, 10);
      } catch {}
    }

    jobs.push({
      source: "linkedin",
      title,
      company,
      location: loc,
      link,
      posted_date: postedDate,
      early_applicant: false,
    });
  }

  return jobs;
}

async function trySearchApi(
  keywords: string,
  location: string,
  seenLinks: Set<string>,
  deadline: number
): Promise<TrackerJob[]> {
  const jobs: TrackerJob[] = [];
  const PAGE_SIZE = 25;
  const TARGET_JOBS = 30;

  for (let page = 0; page < 3; page++) {
    if (jobs.length >= TARGET_JOBS || Date.now() > deadline) break;

    const start = page * PAGE_SIZE;
    const params = new URLSearchParams({
      keywords,
      start: String(start),
      sortBy: "DD",
      f_TPR: "r604800",
    });
    if (location) params.set("location", location);

    try {
      const html = await fetchLinkedIn(`${SEARCH_API}?${params}`, "api");
      if (!html || html.trim().length < 500) break;

      const pageJobs = parseHtmlCards(html, seenLinks);
      if (pageJobs.length === 0) break;
      jobs.push(...pageJobs);
    } catch {
      break;
    }
  }

  return jobs;
}

async function tryRssEndpoint(keywords: string, location: string, seenLinks: Set<string>): Promise<TrackerJob[]> {
  const params = new URLSearchParams({
    keywords,
    f_TPR: "r604800",
    f_E: "1,2,3",
    sortBy: "DD",
    format: "rss",
  });
  if (location) params.set("location", location);

  try {
    const xml = await fetchLinkedIn(`${RSS_SEARCH_URL}?${params}`, "html");
    if (!xml || xml.trim().length < 200) return [];
    return parseRssResults(xml, seenLinks);
  } catch {
    return [];
  }
}

async function tryMainSearchPage(keywords: string, location: string, seenLinks: Set<string>): Promise<TrackerJob[]> {
  const params = new URLSearchParams({
    keywords,
    f_TPR: "r604800",
    f_E: "1,2,3",
    sortBy: "DD",
  });
  if (location) params.set("location", location);

  try {
    const html = await fetchLinkedIn(`${RSS_SEARCH_URL}?${params}`, "html");
    if (!html || html.trim().length < 500) return [];

    const results: TrackerJob[] = [];
    const cardRegex = /<div[^>]*class="[^"]*base-card[^"]*"[^>]*>[\s\S]*?<\/div>\s*<\/div>\s*<\/div>\s*<\/div>/g;
    let match: RegExpExecArray | null;

    while ((match = cardRegex.exec(html)) !== null) {
      const cardHtml = match[0];

      const titleMatch = cardHtml.match(
        /class="[^"]*base-search-card__title[^"]*"[^>]*>([\s\S]*?)<\/h3>/
      );
      const title = cleanText(titleMatch?.[1]);
      if (!title) continue;

      const companyMatch = cardHtml.match(
        /class="[^"]*base-search-card__subtitle[^"]*"[^>]*>([\s\S]*?)<\/h4/
      );
      const company = cleanText(
        companyMatch?.[1]?.replace(/<[^>]+>/g, "")
      );

      const locationMatch = cardHtml.match(
        /class="[^"]*job-search-card__location[^"]*"[^>]*>([^<]+)/
      );
      const loc = cleanText(locationMatch?.[1]);

      const linkMatch = cardHtml.match(
        /href="(https:\/\/www\.linkedin\.com\/jobs\/view\/[^"?]+)/
      );
      const link = linkMatch?.[1] || null;

      if (link && seenLinks.has(link)) continue;
      if (link) seenLinks.add(link);

      let postedDate: string | null = null;
      const timeMatch = cardHtml.match(/datetime="([^"]+)"/);
      if (timeMatch?.[1]) {
        try {
          postedDate = new Date(timeMatch[1]).toISOString().slice(0, 10);
        } catch {}
      }

      results.push({
        source: "linkedin",
        title,
        company,
        location: loc,
        link,
        posted_date: postedDate,
        early_applicant: false,
      });
    }

    return results;
  } catch {
    return [];
  }
}

function parseRapidApiJob(raw: any): TrackerJob | null {
  const title = cleanText(raw.title);
  if (!title) return null;

  const company = cleanText(raw.company ?? raw.companyName);
  const location = cleanText(raw.location);
  const link = raw.url || raw.link || raw.applyUrl || raw.referenceUrl || null;

  let postedDate: string | null = null;
  const rawDate = raw.postedDate ?? raw.postAt ?? raw.listedAt;
  if (rawDate) {
    try {
      postedDate = new Date(rawDate).toISOString().slice(0, 10);
    } catch {}
  }

  return {
    source: "linkedin",
    title,
    company,
    location,
    link,
    posted_date: postedDate,
    description: cleanText(raw.description),
    early_applicant: false,
  };
}

// LinkedIn's own guest/scraping endpoints are rate-limited per Cloudflare
// Workers' shared egress IP pool (see LINKEDIN_SETUP.md history) — no
// amount of retry tuning fixes that, since Workers can't rotate source IPs.
// If a RapidAPI key is configured (same "linkedin-data-api" service the
// Python CLI backend already supports — see backend/cli/linkedin_tracker.py)
// route through that instead: it's RapidAPI's own infrastructure making the
// LinkedIn request, not this Worker's IP, so it isn't subject to the block.
async function searchLinkedInRapidApi(
  keywords: string,
  location: string,
  apiKey: string
): Promise<TrackerJob[]> {
  const params = new URLSearchParams({
    keywords,
    locationId: location || "",
    datePosted: "past-week",
    sort: "recent",
  });

  const resp = await fetchWithTimeout(`${RAPIDAPI_URL}?${params}`, {
    "X-RapidAPI-Key": apiKey,
    "X-RapidAPI-Host": "linkedin-data-api.p.rapidapi.com",
  });

  if (!resp.ok) throw new Error(`LinkedIn RapidAPI HTTP ${resp.status}`);

  const data = (await resp.json()) as any;
  const items = data?.data || [];
  const jobs: TrackerJob[] = [];
  for (const item of items) {
    const job = parseRapidApiJob(item);
    if (job) jobs.push(job);
  }
  return jobs;
}

const BROWSER_NAV_TIMEOUT_MS = 8000;
const BROWSER_MAX_PAGES = 3;
const BROWSER_TARGET_JOBS = 30;
const BROWSER_PAGE_SIZE = 25;

// Real headless Chrome via Cloudflare Browser Rendering, as a free,
// Cloudflare-native fallback when no RapidAPI key is configured. This is a
// DIFFERENT fix than the RapidAPI path: LinkedIn's block on plain fetch()
// here is IP-volume rate-limiting (429s), not the TLS-fingerprint checks
// that Glassdoor uses — and Browser Rendering runs on a different
// Cloudflare egress IP pool than Workers' own fetch(), so it may not be
// caught by the same rate limit.
//
// Uses the shared browser session (lib/shared-browser.ts) rather than
// launching its own — Foundit also needs Browser Rendering for the same
// reason, and independent launches compete for the account's single
// concurrency slot. This only opens its own page within that session and
// never closes the browser itself; the shared session owns that lifecycle.
//
// Paginates within the SAME page (cheap — just another navigation, no new
// browser launch) since a single page's worth of raw jobs (LinkedIn often
// returns closer to 10 than the nominal 25) isn't enough inventory to give
// this source a fair share once results are round-robin interleaved with
// every other active platform in search.ts.
async function searchLinkedInBrowserRendering(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  const browser = await (env.getSharedBrowser ? env.getSharedBrowser() : puppeteer.launch(env.BROWSER));
  const page = await browser.newPage();
  try {
    const seenLinks = new Set<string>();
    const jobs: TrackerJob[] = [];
    const pageLoopDeadline = Date.now() + 10000;

    for (let i = 0; i < BROWSER_MAX_PAGES; i++) {
      if (jobs.length >= BROWSER_TARGET_JOBS || Date.now() > pageLoopDeadline) break;

      const params = new URLSearchParams({
        keywords,
        start: String(i * BROWSER_PAGE_SIZE),
        sortBy: "DD",
        f_TPR: "r604800",
      });
      if (location) params.set("location", location);

      const resp = await page.goto(`${SEARCH_API}?${params}`, {
        waitUntil: "domcontentloaded",
        timeout: BROWSER_NAV_TIMEOUT_MS,
      });
      if (!resp || !resp.ok()) {
        if (i === 0) {
          throw new Error(`LinkedIn Browser Rendering HTTP ${resp ? resp.status() : "no response"}`);
        }
        break; // later pages failing isn't fatal — keep what we already have
      }

      const html = await page.content();
      if (!html || html.trim().length < 500) break;

      const pageJobs = parseHtmlCards(html, seenLinks);
      if (pageJobs.length === 0) break; // no more results to page through
      jobs.push(...pageJobs);
    }

    return jobs;
  } finally {
    await page.close();
  }
}

// Whole-function budget covering EVERY stage (RapidAPI, Browser Rendering,
// and the plain-fetch fallbacks) — leaves a buffer under trackers/index.ts's
// outer race so a slow early stage doesn't leave a doomed later stage no
// time to even try (and still get counted as "timeout" instead of a clean
// partial result), and so the outer race is unlikely to abandon this
// function mid-flight (which would risk the Browser Rendering session never
// getting its browser.close() cleanup run).
const OVERALL_DEADLINE_MS = 16000;

export async function searchLinkedInRss(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  const deadline = Date.now() + OVERALL_DEADLINE_MS;

  if (env.RAPID_API_KEY) {
    try {
      const jobs = await searchLinkedInRapidApi(keywords, location, env.RAPID_API_KEY);
      if (jobs.length > 0) {
        console.log(`[LinkedIn] RapidAPI returned ${jobs.length} jobs`);
        return jobs;
      }
      console.warn("[LinkedIn] RapidAPI returned 0 jobs, falling back to free scraping");
    } catch (e: any) {
      console.warn(`[LinkedIn] RapidAPI failed: ${e.message}, falling back to free scraping`);
    }
  }

  // Two attempts: the account's Browser Rendering concurrency limit is tight
  // enough that back-to-back requests routinely get rejected even though
  // only one session is ever open at a time here — the previous session
  // just hasn't finished releasing yet. A short wait usually clears that,
  // and it's worth it: the plain-fetch fallback below is subject to the
  // same LinkedIn IP-block Browser Rendering exists to avoid.
  for (let attempt = 1; attempt <= 2; attempt++) {
    if (Date.now() >= deadline) break;
    try {
      const jobs = await searchLinkedInBrowserRendering(keywords, location, env);
      if (jobs.length > 0) {
        console.log(`[LinkedIn] Browser Rendering returned ${jobs.length} jobs`);
        return jobs;
      }
      console.warn("[LinkedIn] Browser Rendering returned 0 jobs");
      break; // a clean empty result isn't worth retrying — move to fallback
    } catch (e: any) {
      const isConcurrencyLimit = /rate limit exceeded/i.test(e?.message || "");
      console.warn(`[LinkedIn] Browser Rendering failed: ${e.message}`);
      if (!isConcurrencyLimit || attempt === 2) break;
      await sleep(3000);
    }
  }

  const seenLinks = new Set<string>();
  let jobs: TrackerJob[] = [];

  if (Date.now() < deadline) {
    try {
      jobs = await trySearchApi(keywords, location, seenLinks, deadline);
      console.log(`[LinkedIn] Search API returned ${jobs.length} jobs`);
    } catch (e: any) {
      console.warn(`[LinkedIn] Search API failed: ${e.message}`);
    }
  }

  if (jobs.length < 5 && Date.now() < deadline) {
    try {
      const rssJobs = await tryRssEndpoint(keywords, location, seenLinks);
      console.log(`[LinkedIn] RSS endpoint returned ${rssJobs.length} jobs`);
      jobs.push(...rssJobs);
    } catch {}
  }

  if (jobs.length < 5 && Date.now() < deadline) {
    try {
      const pageJobs = await tryMainSearchPage(keywords, location, seenLinks);
      console.log(`[LinkedIn] Main page returned ${pageJobs.length} jobs`);
      jobs.push(...pageJobs);
    } catch {}
  }

  return jobs;
}
