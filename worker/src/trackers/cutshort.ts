import type { Env, TrackerJob } from "../types";
import { fetchWithTimeout } from "../lib/fetch-timeout";
import { locationMatches } from "../lib/city-aliases";

const BASE = "https://cutshort.io";

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  Accept: "text/html,application/xhtml+xml",
  "Accept-Language": "en-US,en;q=0.9",
};

// The previous implementation used Algolia (app id 8V1WX10EA3) to resolve
// keywords to a job listing — that subdomain no longer resolves at all
// (DNS failure), meaning Cutshort dropped Algolia entirely at some point.
// Their unauthenticated /search-jobs page now only returns placeholder
// "demo" data (query key "getSearchDemoJobs", always 0 results) — real
// free-text search appears to require login.
//
// What still works, unauthenticated: a fixed set of curated SEO category
// pages (/jobs/<slug>), each server-rendering real listings (~50 jobs) in
// __NEXT_DATA__. There's no per-keyword page — only these broad categories
// — so search keywords are mapped to the closest category, then the
// category's jobs are filtered by whether the keyword actually appears in
// the job's title/skills (categories are broad; e.g. "backend-developer-
// jobs" contains Java, Go and Python roles together).
const CATEGORIES: { slug: string; keywords: string[] }[] = [
  { slug: "frontend-developer-jobs", keywords: ["frontend", "front end", "react", "angular", "vue", "javascript", "css", "html", "ui developer"] },
  { slug: "backend-developer-jobs", keywords: ["backend", "back end", "python", "java", "node", "golang", "go developer", "ruby", "php", "api", "server", "django", "flask", "spring"] },
  { slug: "android-developer-jobs", keywords: ["android", "kotlin"] },
  { slug: "ios-developer-jobs", keywords: ["ios", "swift", "objective-c", "objective c"] },
  { slug: "devops-jobs", keywords: ["devops", "sre", "site reliability", "kubernetes", "docker", "cloud engineer", "infrastructure"] },
  { slug: "datascience-jobs", keywords: ["data scientist", "data science", "machine learning", "ml engineer", "ai engineer", "data analyst", "data engineer"] },
  { slug: "product-manager-jobs", keywords: ["product manager", "product owner"] },
  { slug: "ux-design-jobs", keywords: ["ux", "ui design", "designer", "product design", "graphic design"] },
  { slug: "digital-marketing-jobs", keywords: ["digital marketing", "seo", "sem", "growth marketing"] },
  { slug: "marketing-sales-jobs", keywords: ["sales", "marketing", "business development"] },
  { slug: "content-writing-jobs", keywords: ["content writ", "copywrit", "technical writ"] },
  { slug: "video-editing-jobs", keywords: ["video edit", "video producer"] },
  { slug: "internet-of-things-iot-jobs", keywords: ["iot", "embedded", "firmware"] },
];
const FALLBACK_SLUG = "startup-jobs";

function pickCategory(keywords: string): string {
  const lower = keywords.toLowerCase();
  for (const cat of CATEGORIES) {
    if (cat.keywords.some((kw) => lower.includes(kw))) return cat.slug;
  }
  return FALLBACK_SLUG;
}

function cleanText(v: any): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s ? s : null;
}

function formatSalary(range: any): string | null {
  const min = range?.userMinVanity ?? range?.min;
  const max = range?.userMaxVanity ?? range?.max;
  if (!max) return null;
  const fmt = (n: number) => (n >= 100000 ? `${(n / 100000).toFixed(1).replace(/\.0$/, "")}L` : String(n));
  return min ? `₹${fmt(min)} - ${fmt(max)}` : `Up to ₹${fmt(max)}`;
}

function jobMatchesKeywords(job: any, keywords: string): boolean {
  const terms = keywords.toLowerCase().split(/\s+/).filter((t) => t.length > 2);
  if (!terms.length) return true;
  const haystack = [job.headline, ...(job.allSkills || [])].join(" ").toLowerCase();
  return terms.some((t) => haystack.includes(t));
}

function parseJob(job: any): TrackerJob | null {
  const title = cleanText(job.headline);
  if (!title) return null;

  const locations = Array.isArray(job.locations) ? job.locations : [];

  return {
    source: "cutshort",
    title,
    company: cleanText(job.companyDetails?.name),
    location: locations.join(", ") || null,
    link: job.publicUrl || null,
    posted_date: null, // Cutshort doesn't expose posting dates on this page
    salary: formatSalary(job.salaryRange),
    experience: job.expRange?.min != null ? `${job.expRange.min}+ yrs` : null,
  };
}

export async function searchCutshort(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  const slug = pickCategory(keywords);
  const resp = await fetchWithTimeout(`${BASE}/jobs/${slug}`, {
    headers: HEADERS,
    cf: { cacheTtl: 300 },
  });

  if (!resp.ok) {
    if (resp.status === 404) return [];
    throw new Error(`Cutshort HTTP ${resp.status}`);
  }

  const html = await resp.text();
  const nextDataMatch = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!nextDataMatch?.[1]) return [];

  let rawJobs: any[];
  try {
    const nextData = JSON.parse(nextDataMatch[1]);
    rawJobs = nextData?.props?.pageProps?.dehydratedState?.queries?.[0]?.state?.data?.data?.pageData?.jobs;
    if (!Array.isArray(rawJobs)) return [];
  } catch {
    return [];
  }

  const jobs: TrackerJob[] = [];
  for (const raw of rawJobs) {
    if (!jobMatchesKeywords(raw, keywords)) continue;
    if (location) {
      const locs: string[] = Array.isArray(raw.locations) ? raw.locations : [];
      if (locs.length && !locs.some((l) => locationMatches(location, l))) continue;
    }
    const job = parseJob(raw);
    if (job) jobs.push(job);
  }

  return jobs;
}
