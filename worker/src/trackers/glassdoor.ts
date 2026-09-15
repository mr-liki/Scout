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
async function searchGlassdoorViaOwnProxy(
  keywords: string,
  location: string,
  proxyUrl: string,
  proxyKey: string
): Promise<TrackerJob[]> {
  const params = new URLSearchParams({ query: keywords });
  if (location) params.set("location", location);

  // Render's free tier spins down after ~15 min idle and can take 30-60s to
  // wake — this won't wait that long (would blow the tracker's own ~19s
  // ceiling anyway), so a cold start here just falls through to the direct
  // request below, same as any other failure.
  const resp = await fetchWithTimeout(`${proxyUrl.replace(/\/$/, "")}/glassdoor?${params}`, {
    headers: { "x-proxy-key": proxyKey },
  }, 15000);
  if (!resp.ok) throw new Error(`Glassdoor own-proxy HTTP ${resp.status}`);

  const html = await resp.text();
  return parseGlassdoorHtml(html);
}

export async function searchGlassdoor(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  if (env.GLASSDOOR_PROXY_URL && env.GLASSDOOR_PROXY_KEY) {
    try {
      const jobs = await searchGlassdoorViaOwnProxy(keywords, location, env.GLASSDOOR_PROXY_URL, env.GLASSDOOR_PROXY_KEY);
      console.log(`[Glassdoor] Own proxy returned ${jobs.length} jobs`);
      if (jobs.length > 0) return jobs;
    } catch (e: any) {
      console.warn(`[Glassdoor] Own proxy failed: ${e.message}, falling back to direct fetch`);
    }
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
