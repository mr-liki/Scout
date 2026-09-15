import type { Env, TrackerJob } from "../types";
import { fetchWithTimeout } from "../lib/fetch-timeout";
import { locationMatches } from "../lib/city-aliases";

const API_URL = "https://www.shine.com/api/v2/search/simple/";
const JOB_BASE = "https://www.shine.com/jobs/";

const FIELD_LIST =
  "id,jJD,jHF,jCID,jCL,jLU,jPack,jSlug,is_shortlisted,jRUrl,jPDate,jKwd," +
  "jCName,jJT,jLoc,jInd,jExp,is_applied,jRR,jJobType,jExpDate,jRP,jRE," +
  "jHCD,jHRPBA,jAC,jPJ,jHJ,jTypeC,jEType,jQL,jSJ,jVanc,early_applicant_badge," +
  "jCrwSt,jSLA,jSal,jWM,jJBL";

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
  Accept: "application/json",
  "Accept-Language": "en-US,en;q=0.9",
};

function cleanText(v: any): string | null {
  if (v == null) return null;
  const s = String(v).replace(/<[^>]+>/g, " ").trim();
  return s ? s : null;
}

function parseJob(raw: any): TrackerJob {
  const slug = raw.jSlug;
  const link = slug ? `${JOB_BASE}${slug}` : "";
  const locations = raw.jLoc || [];
  const location = Array.isArray(locations) ? locations.join(", ") : "";

  let salary = cleanText(raw.jSal);
  if (
    salary &&
    ["not disclosed", "not mentioned", "[salary hidden]", "salary hidden"].includes(
      salary.toLowerCase()
    )
  ) {
    salary = null;
  }

  // Parse IST posted date to YYYY-MM-DD
  let postedDate: string | null = null;
  const rawDate = raw.jPDate;
  if (rawDate) {
    try {
      const dt = new Date(rawDate);
      if (!isNaN(dt.getTime())) {
        postedDate = dt.toISOString().slice(0, 10);
      }
    } catch {}
  }

  return {
    source: "shine",
    title: cleanText(raw.jJT) || "N/A",
    company: cleanText(raw.jCName) || "N/A",
    location,
    link,
    posted_date: postedDate,
    salary,
    experience: cleanText(raw.jExp),
    early_applicant: Boolean(raw.early_applicant_badge),
  };
}

async function resolveLocation(
  keywords: string,
  location: string
): Promise<string | null> {
  if (!location) return null;

  const params = new URLSearchParams({
    q: keywords,
    qActual: keywords,
    fl: FIELD_LIST,
    show_learning_products: "false",
    url: keywords,
    only_facet: "true",
    expansion: "true",
    expert_edge_flag: "true",
  });

  try {
    const resp = await fetchWithTimeout(`${API_URL}?${params}`, { headers: HEADERS });
    if (!resp.ok) return null;
    const data = (await resp.json()) as any;
    const candidates = data?.facets?.fields?.jFLoc;
    if (!candidates?.length) return null;

    const match = candidates.find((c: any) => locationMatches(location, String(c[2])));
    return match ? String(match[0]) : null;
  } catch {
    return null;
  }
}

export async function searchShine(
  keywords: string,
  location: string,
  env: Env
): Promise<TrackerJob[]> {
  const locId = await resolveLocation(keywords, location);

  const params = new URLSearchParams({
    q: keywords,
    qActual: keywords,
    fl: FIELD_LIST,
    show_learning_products: "false",
    url: keywords,
    only_facet: "false",
    expansion: "true",
    expert_edge_flag: "true",
    page: "1",
  });
  if (locId) params.set("location", locId);

  const resp = await fetchWithTimeout(`${API_URL}?${params}`, {
    headers: HEADERS,
    cf: { cacheTtl: 60 },
  });
  if (!resp.ok) throw new Error(`Shine HTTP ${resp.status}`);

  const data = (await resp.json()) as any;
  const results = data?.results || [];

  return results.map(parseJob).filter(Boolean);
}
