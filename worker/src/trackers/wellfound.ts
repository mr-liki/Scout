import type { Env, TrackerJob } from "../types";
import { fetchWithTimeout } from "../lib/fetch-timeout";

const BASE = "https://wellfound.com";

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  Accept: "text/html,application/xhtml+xml",
  "Accept-Language": "en-US,en;q=0.9",
};

// Wellfound uses SEO role pages with embedded Apollo state in __NEXT_DATA__
// e.g. /role/python-developer/bengaluru
function buildSlug(keywords: string): string {
  return keywords
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function buildLocationSlug(location: string): string {
  return location
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function parseJob(node: any): TrackerJob | null {
  // Apollo state nodes have __typename: "JobPosting"
  if (!node || node.__typename !== "JobPosting") return null;

  const title = node.title;
  if (!title) return null;

  const companyName = node.startup?.name || node.companyName || null;
  const locationName =
    node.remoteness ||
    node.locationName ||
    node.startup?.locationName ||
    null;

  const link = node.absoluteUrl
    ? `${BASE}${node.absoluteUrl}`
    : node.id
    ? `${BASE}/jobs/${node.id}`
    : null;

  // Posted date — Wellfound uses createdAt
  let postedDate: string | null = null;
  if (node.createdAt) {
    try {
      postedDate = new Date(node.createdAt).toISOString().slice(0, 10);
    } catch {}
  }

  const salary = node.salary || null;
  const experience = node.experienceLevel || null;

  return {
    source: "wellfound",
    title,
    company: companyName,
    location: locationName,
    link,
    posted_date: postedDate,
    salary,
    experience,
  };
}

export async function searchWellfound(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  const roleSlug = buildSlug(keywords);
  let url = `${BASE}/role/${roleSlug}`;
  if (location) {
    url += `/${buildLocationSlug(location)}`;
  }

  const resp = await fetchWithTimeout(url, {
    headers: HEADERS,
    redirect: "follow",
    cf: { cacheTtl: 120 },
  });

  if (!resp.ok) {
    // 404 is common for unmapped role slugs — not an error
    if (resp.status === 404) return [];
    throw new Error(`Wellfound HTTP ${resp.status}`);
  }

  const html = await resp.text();

  // Extract __NEXT_DATA__ JSON
  const nextDataMatch = html.match(
    /<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/
  );
  if (!nextDataMatch?.[1]) return [];

  try {
    const nextData = JSON.parse(nextDataMatch[1]);
    const apolloState = nextData?.props?.pageProps?.apolloState;
    if (!apolloState) return [];

    const jobs: TrackerJob[] = [];
    for (const key of Object.keys(apolloState)) {
      const node = apolloState[key];
      const job = parseJob(node);
      if (job) jobs.push(job);
    }

    return jobs.slice(0, 25);
  } catch {
    return [];
  }
}
