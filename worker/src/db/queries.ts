import type { Env, Job, TrackerJob } from "../types";
import { makeJobId } from "../lib/search-merge";

const SOURCE_DISPLAY: Record<string, string> = {
  linkedin: "LinkedIn",
  indeed: "Indeed",
  glassdoor: "Glassdoor",
  wellfound: "Wellfound",
  naukri: "Naukri",
  foundit: "Foundit",
  shine: "Shine",
  cutshort: "Cutshort",
  apna: "Apna",
};

export function displayName(source: string): string {
  return SOURCE_DISPLAY[source] || source;
}

export async function upsertJobs(db: D1Database, jobs: TrackerJob[]): Promise<number> {
  if (!jobs.length) return 0;

  const stmt = db.prepare(
    `INSERT INTO jobs (id, source, title, company, location, link, posted_date, salary, description, experience, easy_apply, early_applicant, remote, company_rating, applicants, first_seen_at, last_seen_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, datetime('now'), datetime('now'))
     ON CONFLICT(id) DO UPDATE SET
       title=excluded.title, company=excluded.company, location=excluded.location,
       link=excluded.link, posted_date=excluded.posted_date, salary=excluded.salary,
       description=excluded.description, experience=excluded.experience,
       easy_apply=excluded.easy_apply, early_applicant=excluded.early_applicant,
       remote=excluded.remote, company_rating=excluded.company_rating,
       applicants=excluded.applicants, last_seen_at=datetime('now')`
  );

  const batch = jobs.map((j) => {
    const id = makeJobId(j.source, j.title || "", j.company || "", j.link || "");
    return stmt.bind(
      id,
      j.source,
      j.title || "",
      j.company || null,
      j.location || null,
      j.link || null,
      j.posted_date || null,
      j.salary || null,
      j.description || null,
      j.experience || null,
      j.easy_apply ? 1 : 0,
      j.early_applicant ? 1 : 0,
      j.remote ? 1 : 0,
      j.company_rating || null,
      j.applicants || null
    );
  });

  const results = await db.batch(batch);
  return results.length;
}

export async function searchJobs(
  db: D1Database,
  keywords: string,
  location: string,
  limit: number = 100
): Promise<Job[]> {
  const terms = keywords
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  if (!terms.length) return [];

  // Relevance: every keyword must match the title. Matching only the
  // company/description let unrelated jobs (e.g. any listing that merely
  // mentions "python" in its description) leak into results for other
  // queries once enough rows accumulated in D1.
  let query = `SELECT * FROM jobs WHERE `;
  const queryBindings: string[] = [];
  let idx = 1;

  for (const term of terms) {
    query += `(lower(title) LIKE ?${idx})`;
    if (term !== terms[terms.length - 1] || location) query += " AND ";
    queryBindings.push(`%${term}%`);
    idx++;
  }

  if (location) {
    const locTerms = location
      .toLowerCase()
      .split(/\s*,?\s+/)
      .filter(Boolean);
    for (const lt of locTerms) {
      query += `lower(location) LIKE ?${idx}`;
      if (lt !== locTerms[locTerms.length - 1]) query += " AND ";
      queryBindings.push(`%${lt}%`);
      idx++;
    }
  }

  query += ` ORDER BY last_seen_at DESC LIMIT ?${idx}`;
  queryBindings.push(String(limit));

  const result = await db.prepare(query).bind(...queryBindings).all<Job>();
  return result.results || [];
}

export async function updateScrapeStatus(
  db: D1Database,
  source: string,
  jobsCount: number,
  error?: string
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO scrape_status (source, last_run, last_success, jobs_count, error)
       VALUES (?1, datetime('now'), datetime('now'), ?2, ?3)
       ON CONFLICT(source) DO UPDATE SET
         last_run=datetime('now'),
         last_success=CASE WHEN ?3 IS NULL THEN datetime('now') ELSE last_success END,
         jobs_count=?2, error=?3`
    )
    .bind(source, jobsCount, error || null)
    .run();
}

export async function getScrapeStatuses(db: D1Database): Promise<Record<string, any>> {
  const result = await db.prepare("SELECT * FROM scrape_status").all();
  const status: Record<string, any> = {};
  for (const row of result.results || []) {
    status[row.source as string] = row;
  }
  return status;
}
