import type { Env, TrackerJob } from "../types";
import { fetchWithTimeout } from "../lib/fetch-timeout";

const SEARCH_URL = "https://www.glassdoor.com/Job/jobs.htm";
const JOBS_BASE = "https://www.glassdoor.com";

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  Accept:
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.9",
  "Accept-Encoding": "gzip, deflate, br",
  "Cache-Control": "no-cache",
};

function cleanText(v: any): string | null {
  if (v == null) return null;
  const s = String(v).replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").trim();
  return s ? s : null;
}

function parseJob(cardHtml: string): TrackerJob | null {
  // Extract title — current markup: <a class="JobCard_jobTitle__..."
  // data-test="job-title">Title</a>. This selector still matches; the
  // company/location ones below had gone stale (see comment further down).
  const titleMatch = cardHtml.match(
    /data-test="job-title"[^>]*>([^<]+)/
  ) || cardHtml.match(
    /class="[^"]*jobTitle[^"]*"[^>]*>[\s\S]*?<a[^>]*>([^<]+)/
  );
  const title = cleanText(titleMatch?.[1]);
  if (!title) return null;

  // Extract company — current markup:
  // <span class="EmployerProfile_compactEmployerName__...">Name</span>
  const companyMatch = cardHtml.match(
    /class="[^"]*EmployerProfile_compactEmployerName[^"]*"[^>]*>([^<]+)/
  ) || cardHtml.match(
    /data-test="employer-short-name"[^>]*>([^<]+)/
  ) || cardHtml.match(
    /class="[^"]*employer[^"]*"[^>]*>([^<]+)/
  );
  const company = cleanText(companyMatch?.[1]);

  // Extract location — current markup:
  // <div class="JobCard_location__..." data-test="emp-location">City</div>
  const locationMatch = cardHtml.match(
    /data-test="emp-location"[^>]*>([^<]+)/
  ) || cardHtml.match(
    /data-test="job-location"[^>]*>([^<]+)/
  ) || cardHtml.match(
    /class="[^"]*location[^"]*"[^>]*>([^<]+)/
  );
  const location = cleanText(locationMatch?.[1]);

  // Extract link
  const linkMatch = cardHtml.match(
    /href="(\/job\/[^"]+)"/
  );
  const link = linkMatch?.[1]
    ? `${JOBS_BASE}${linkMatch[1]}`
    : null;

  // Extract salary if shown
  const salaryMatch = cardHtml.match(
    /class="[^"]*salary[^"]*"[^>]*>([^<]+)/
  );
  const salary = cleanText(salaryMatch?.[1]);

  return {
    source: "glassdoor",
    title,
    company,
    location,
    link,
    posted_date: null,
    salary,
  };
}

function parseGlassdoorHtml(html: string): TrackerJob[] {
  const jobs: TrackerJob[] = [];

  // Parse job cards — Glassdoor uses data-test attributes
  const cardRegex =
    /<li[^>]*class="[^"]*JobsList_jobListItem[^"]*"[^>]*>([\s\S]*?)<\/li>/g;
  let match: RegExpExecArray | null;

  while ((match = cardRegex.exec(html)) !== null) {
    const job = parseJob(match[1]);
    if (job) jobs.push(job);
  }

  // Fallback: try other card patterns
  if (!jobs.length) {
    const altRegex =
      /<div[^>]*data-test="job-card[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<\/div>/g;
    while ((match = altRegex.exec(html)) !== null) {
      const job = parseJob(match[1]);
      if (job) jobs.push(job);
    }
  }

  return jobs.slice(0, 30);
}

function buildGlassdoorUrl(keywords: string, location: string): string {
  const params = new URLSearchParams({
    "sc.keyword": keywords,
    p: "1",
  });
  if (location) params.set("locT", "");
  if (location) params.set("locId", "");
  if (location) params.set("locKeyword", location);
  return `${SEARCH_URL}?${params}`;
}

// Two earlier fixes both failed against Glassdoor's block the same way
// ("Security | Glassdoor", a TLS/JA3 fingerprint check — see
// GLASSDOOR_SETUP.md): Browser Rendering (real Chrome, real TLS handshake —
// still 403'd) and a JS proxy on Deno Deploy (fixed Foundit's IP-reputation
// block, but Glassdoor's isn't IP-based, so a different network origin
// didn't help). What actually works: curl_cffi's literal Chrome TLS-stack
// impersonation — confirmed directly (200, real job data, 30 cards parsed)
// — which needs a real Python process with a compiled dependency, so it
// runs as glassdoor-proxy/ on Render.com instead (neither Cloudflare
// Workers nor Deno Deploy can execute compiled/native code).
//
// Glassdoor can still rate-limit even a "good" TLS fingerprint if the same
// IP sends enough requests in a short window (observed directly: repeated
// testing during development got the Render proxy's IP temporarily
// 403'd again, clearing on its own ~15 min later). A dedicated, longer-
// lived cache here — independent of the whole-response 60s cache in
// routes/search.ts — means repeat searches for the same query don't keep
// re-hitting Glassdoor at all, which is both faster and reduces the volume
// that could retrigger the same rate limit.
const PROXY_CACHE_TTL_SECONDS = 900; // 15 minutes

function proxyCacheKey(keywords: string, location: string): string {
  return `glassdoor:proxy:${keywords.toLowerCase()}:${location.toLowerCase()}`.slice(0, 200);
}

async function fetchViaProxy(
  keywords: string,
  location: string,
  proxyUrl: string,
  proxyKey: string
): Promise<TrackerJob[]> {
  const params = new URLSearchParams({ query: keywords });
  if (location) params.set("location", location);

  // Render's free tier spins down after ~15 min idle and can take 30-60s to
  // wake — a keep-alive cron (index.ts's scheduled handler) pings all
  // configured instances to prevent that, but this timeout still exists as
  // a safety net so a cold start (or a dead instance) doesn't blow the
  // whole tracker budget — it just moves on to the next proxy in the list.
  const resp = await fetchWithTimeout(`${proxyUrl.replace(/\/$/, "")}/glassdoor?${params}`, {
    headers: { "x-proxy-key": proxyKey },
  }, 12000);
  if (!resp.ok) throw new Error(`Glassdoor own-proxy HTTP ${resp.status}`);

  const html = await resp.text();
  return parseGlassdoorHtml(html);
}

// Glassdoor's rate-limiting is tied to a specific shared IP pool (Render's
// free-tier outbound IPs are shared across many tenants), and different
// Render regions draw from different pools. Rather than depend on one
// region being in good standing, this tries every configured proxy
// instance (deploy the same glassdoor-proxy/ code to 2-3 regions) until
// one succeeds — real infrastructure redundancy against a shared-IP
// problem, not a workaround for the TLS check itself (curl_cffi already
// handles that part, see GLASSDOOR_SETUP.md).
function configuredProxies(env: Env): { url: string; key: string }[] {
  const key = env.GLASSDOOR_PROXY_KEY;
  if (!key) return [];
  const urls = [env.GLASSDOOR_PROXY_URL, env.GLASSDOOR_PROXY_URL_2, env.GLASSDOOR_PROXY_URL_3].filter(
    (u): u is string => Boolean(u)
  );
  return urls.map((url) => ({ url, key }));
}

async function searchGlassdoorViaOwnProxies(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  const proxies = configuredProxies(env);
  if (!proxies.length) return [];

  const cacheKey = proxyCacheKey(keywords, location);
  const cached = await env.KV.get(cacheKey, "json");
  if (cached && Array.isArray(cached)) {
    console.log(`[Glassdoor] Proxy cache hit (${cached.length} jobs)`);
    return cached as TrackerJob[];
  }

  // Shared deadline across all attempts — trying 3 proxies at up to 12s
  // each could otherwise take 36s, well past this tracker's own ~19s
  // ceiling in trackers/index.ts. 16s leaves a buffer under that.
  const deadline = Date.now() + 16000;
  let lastError: Error | null = null;
  for (const { url, key } of proxies) {
    if (Date.now() >= deadline) break;
    try {
      const jobs = await fetchViaProxy(keywords, location, url, key);
      if (jobs.length > 0) {
        try {
          await env.KV.put(cacheKey, JSON.stringify(jobs), { expirationTtl: PROXY_CACHE_TTL_SECONDS });
        } catch {}
        return jobs;
      }
      console.warn(`[Glassdoor] Proxy ${url} returned 0 jobs, trying next`);
    } catch (e: any) {
      console.warn(`[Glassdoor] Proxy ${url} failed: ${e.message}, trying next`);
      lastError = e;
    }
  }

  if (lastError) throw lastError;
  return [];
}

export async function searchGlassdoor(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  try {
    const jobs = await searchGlassdoorViaOwnProxies(keywords, location, env);
    if (jobs.length > 0) {
      console.log(`[Glassdoor] Own proxies returned ${jobs.length} jobs`);
      return jobs;
    }
  } catch (e: any) {
    console.warn(`[Glassdoor] All own proxies failed: ${e.message}, falling back to direct fetch`);
  }

  const resp = await fetchWithTimeout(buildGlassdoorUrl(keywords, location), {
    headers: HEADERS,
    redirect: "follow",
    cf: { cacheTtl: 120 },
  });

  if (!resp.ok) throw new Error(`Glassdoor HTTP ${resp.status}`);

  const html = await resp.text();
  return parseGlassdoorHtml(html);
}
