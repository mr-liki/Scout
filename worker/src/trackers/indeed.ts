import type { Env, TrackerJob } from "../types";
import { fetchWithTimeout } from "../lib/fetch-timeout";

const API_URL = "https://apis.indeed.com/graphql";
const VIEW_JOB = "https://www.indeed.com/viewjob?jk=";

const HEADERS = {
  Host: "apis.indeed.com",
  "content-type": "application/json",
  "indeed-api-key": "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8",
  accept: "application/json",
  "indeed-locale": "en-US",
  "accept-language": "en-US,en;q=0.9",
  "user-agent":
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1",
  "indeed-app-info":
    "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
};

const SALARY_RE =
  /\$\s?\d[\d,]*(?:\.\d+)?(?:[kK])?\s*(?:[-–to]+\s*\$\s?\d[\d,]*(?:\.\d+)?(?:[kK])?)?\s*(?:a\s+|an\s+|per\s+|\/)?(?:year|yr|yearly|hour|hr|hourly|month|mo|monthly|week|wk|weekly|day)\b/i;

function cleanText(v: any): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s ? s : null;
}

function extractSalary(text: string | null): string | null {
  if (!text) return null;
  const match = SALARY_RE.exec(text);
  if (!match) return null;
  const snippet = match[0].replace(/\s+/g, " ").trim();
  return snippet.length > 40 ? null : snippet;
}

function buildQuery(keywords: string, location: string, limit: number): string {
  limit = Math.max(1, Math.min(limit, 50));
  const safeWhat = keywords.replace(/"/g, "'").replace(/\n/g, " ").trim();

  let locBlock = "";
  if (location) {
    const safeLoc = location.replace(/"/g, "'").replace(/\n/g, " ").trim();
    locBlock = `location: {where: "${safeLoc}", radius: 25, radiusUnit: MILES}`;
  }

  return `query JobSearch {
  jobSearch(
    what: "${safeWhat}"
    ${locBlock}
    limit: ${limit}
    sort: RELEVANCE
  ) {
    results {
      trackingKey
      job {
        key
        title
        dateOnIndeed
        location { formatted { short } }
        source { name }
        description { text }
        attributes { label }
      }
    }
  }
}`;
}

function parseJob(raw: any): TrackerJob | null {
  const key = raw.key;
  const title = cleanText(raw.title);
  if (!title) return null;

  let postedDate: string | null = null;
  const dateRaw = raw.dateOnIndeed;
  if (dateRaw) {
    try {
      postedDate = new Date(Number(dateRaw)).toISOString().slice(0, 10);
    } catch {}
  }

  const location = cleanText(
    (raw.location || {}).formatted?.short
  );
  const company = cleanText((raw.source || {}).name);
  const description = cleanText((raw.description || {}).text);

  return {
    source: "indeed",
    title,
    company,
    location,
    link: key ? `${VIEW_JOB}${key}` : null,
    posted_date: postedDate,
    salary: extractSalary(description),
    description,
  };
}

export async function searchIndeed(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  const query = buildQuery(keywords, location, 25);

  const resp = await fetchWithTimeout(API_URL, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify({ query }),
    cf: { cacheTtl: 60 },
  });

  if (!resp.ok) throw new Error(`Indeed HTTP ${resp.status}`);

  const data = (await resp.json()) as any;
  if (data.errors?.length) {
    throw new Error(`Indeed GraphQL: ${data.errors[0].message}`);
  }

  const results = data?.data?.jobSearch?.results || [];
  const jobs: TrackerJob[] = [];

  for (const r of results) {
    const job = parseJob(r.job);
    if (job) jobs.push(job);
  }

  return jobs;
}
