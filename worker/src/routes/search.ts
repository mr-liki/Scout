import type { Env } from "../types";
import { corsHeaders } from "../lib/cors";
import { checkRateLimit } from "../lib/rate-limit";
import { interleaveBySource } from "../lib/search-merge";
import { searchJobs, upsertJobs, updateScrapeStatus } from "../db/queries";
import { searchAllTrackers } from "../trackers";

export async function handleSearch(
  request: Request,
  env: Env
): Promise<Response> {
  const origin = request.headers.get("Origin");
  const headers = corsHeaders(origin, env.ALLOWED_ORIGINS);

  // Rate limit: 20 searches per minute per IP
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const rl = await checkRateLimit(env.KV, `search:${ip}`, 20, 60);
  if (!rl.allowed) {
    return Response.json(
      { error: "Rate limit exceeded", retryAfter: rl.retryAfter },
      { status: 429, headers: { ...headers, "Retry-After": String(rl.retryAfter) } }
    );
  }

  const url = new URL(request.url);
  const keywords = url.searchParams.get("q") || "";
  const location = url.searchParams.get("location") || "";
  const limit = Math.min(Number(url.searchParams.get("limit")) || 50, 200);

  if (!keywords.trim()) {
    return Response.json({ error: "q parameter is required" }, { status: 400, headers });
  }

  // Check KV cache first
  const cacheKey = `search:${keywords.toLowerCase()}:${location.toLowerCase()}`.slice(0, 200);
  const cached = await env.KV.get(cacheKey, "json");
  if (cached) {
    return Response.json(cached, { headers: { ...headers, "X-Cache": "HIT" } });
  }

  // Run all trackers in parallel
  const { jobs: trackerJobs, platforms, errors } = await searchAllTrackers(
    keywords.trim(),
    location.trim(),
    env
  );

  // Upsert into D1
  if (trackerJobs.length) {
    try {
      await upsertJobs(env.DB, trackerJobs);
      for (const [src, count] of Object.entries(platforms)) {
        await updateScrapeStatus(env.DB, src, count);
      }
    } catch (e: any) {
      errors.push(`D1 write: ${e.message}`);
    }
  }

  // Also pull from D1, but only for sources that didn't return live results —
  // sources with live results are already fresh and accurate; falling back
  // to stale D1 rows for those would just reintroduce irrelevant old jobs.
  let allJobs = trackerJobs;
  const liveSources = new Set(Object.keys(platforms));
  try {
    const d1Jobs = await searchJobs(env.DB, keywords.trim(), location.trim(), limit);
    // Merge: live results + D1 results, dedupe by id
    const seen = new Set(allJobs.map((j) => `${j.source}|${j.title}|${j.company}`));
    for (const dj of d1Jobs) {
      if (liveSources.has(dj.source)) continue;
      const key = `${dj.source}|${dj.title}|${dj.company}`;
      if (!seen.has(key)) {
        seen.add(key);
        allJobs.push({
          source: dj.source,
          title: dj.title,
          company: dj.company,
          location: dj.location,
          link: dj.link,
          posted_date: dj.posted_date,
          salary: dj.salary,
          description: dj.description,
          experience: dj.experience,
          easy_apply: Boolean(dj.easy_apply),
          early_applicant: Boolean(dj.early_applicant),
          remote: Boolean(dj.remote),
        });
      }
    }
  } catch (e: any) {
    errors.push(`D1 read: ${e.message}`);
  }

  // Interleave by source, THEN take the limit
  const displayJobs = interleaveBySource(
    allJobs.map((j, i) => ({
      ...j,
      id: `${j.source}-${i}`,
      source: j.source,
      posted_date: j.posted_date || null,
      first_seen_at: "",
      last_seen_at: "",
    }))
  ).slice(0, limit);

  const response = {
    query: { keywords: keywords.trim(), location: location.trim() },
    jobs: displayJobs,
    platforms,
    total: displayJobs.length,
    errors,
    searched_at: new Date().toISOString(),
  };

  // Cache for 60 seconds
  await env.KV.put(cacheKey, JSON.stringify(response), { expirationTtl: 60 });

  return Response.json(response, { headers: { ...headers, "X-Cache": "MISS" } });
}
