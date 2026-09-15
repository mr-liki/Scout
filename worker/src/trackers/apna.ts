import type { Env, TrackerJob } from "../types";
import { fetchWithTimeout } from "../lib/fetch-timeout";
import { locationMatches } from "../lib/city-aliases";

const BASE_URL = "https://apna.co";

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  Accept: "text/html,application/xhtml+xml",
  "Accept-Language": "en-US,en;q=0.9",
};

function cleanText(v: any): string | null {
  if (v == null) return null;
  const s = String(v).replace(/<[^>]+>/g, " ").trim();
  return s ? s : null;
}

// Apna's site is Next.js App Router with React Server Components — there is
// no client-side XHR/API call to find (confirmed by watching real network
// traffic: the /jobs search page's own GET response is the only substantive
// request). Real job data comes back as a JSON blob embedded — as an
// escaped string — inside `self.__next_f.push([1,"..."])` RSC payload
// chunks in that same HTML response. It has a clean, stable shape once
// unescaped: {"jobID":..,"jobTitle":"..","jobOrganisationDetails":
// {"organisationName":".."},"jobPublicURL":"..","jobSalaryRangeDetails":
// {"salaryMax":..,"salaryMin":..},"jobCardAddress":".."}. The old
// JSON-LD/CSS-class scraping this file used to do no longer matches
// anything on the current site.
const PUSH_CHUNK_RE = /self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)/g;

function extractRscText(html: string): string {
  let combined = "";
  let m: RegExpExecArray | null;
  PUSH_CHUNK_RE.lastIndex = 0;
  while ((m = PUSH_CHUNK_RE.exec(html)) !== null) {
    try {
      combined += JSON.parse(`"${m[1]}"`);
    } catch {
      // A chunk that doesn't decode cleanly as a JSON string literal just
      // gets skipped — job data lives in more than one chunk, so losing one
      // isn't fatal.
    }
  }
  return combined;
}

function parseJobsFromRscText(text: string): TrackerJob[] {
  const jobs: TrackerJob[] = [];
  const idRe = /"jobID":(\d+)/g;
  let m: RegExpExecArray | null;

  while ((m = idRe.exec(text)) !== null) {
    const chunk = text.slice(m.index, m.index + 2000);

    const title = cleanText(chunk.match(/"jobTitle":"([^"]*)"/)?.[1]);
    if (!title) continue;

    const company = cleanText(chunk.match(/"organisationName":"([^"]*)"/)?.[1]);
    const publicUrl = chunk.match(/"jobPublicURL":"([^"]*)"/)?.[1];
    const address = cleanText(chunk.match(/"jobCardAddress":"([^"]*)"/)?.[1]);

    const salaryMax = chunk.match(/"salaryMax":(\d+|null)/)?.[1];
    const salaryMin = chunk.match(/"salaryMin":(\d+|null)/)?.[1];
    let salary: string | null = null;
    if (salaryMax && salaryMax !== "null" && salaryMax !== "0") {
      salary =
        salaryMin && salaryMin !== "null" && salaryMin !== salaryMax
          ? `₹${salaryMin} - ₹${salaryMax}`
          : `Up to ₹${salaryMax}`;
    }

    const expMatch = chunk.match(/"tagLabel":"(Min\.[^"]*)"/);

    jobs.push({
      source: "apna",
      title,
      company,
      location: address,
      link: publicUrl ? `${BASE_URL}${publicUrl}` : null,
      posted_date: null,
      salary,
      experience: expMatch ? cleanText(expMatch[1]) : null,
    });
  }

  return jobs;
}

export async function searchApna(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  const url = `${BASE_URL}/jobs?search=true&text=${encodeURIComponent(keywords)}`;

  const resp = await fetchWithTimeout(url, {
    headers: HEADERS,
    cf: { cacheTtl: 120 },
  });

  if (!resp.ok) throw new Error(`Apna HTTP ${resp.status}`);

  const html = await resp.text();
  const rscText = extractRscText(html);
  const jobs = parseJobsFromRscText(rscText);

  if (!location) return jobs;
  // Apna's /jobs/jobs-in-<city> URL variant doesn't actually filter
  // server-side (verified: identical top result with or without it), so
  // location filtering happens here instead, against jobCardAddress (which
  // already carries both old/new city names, e.g. "Bengaluru/Bangalore").
  return jobs.filter((j) => !j.location || locationMatches(location, j.location));
}
