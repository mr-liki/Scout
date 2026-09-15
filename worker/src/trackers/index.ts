import type { Env, TrackerJob } from "../types";
import { createSharedBrowser } from "../lib/shared-browser";

export { searchFoundit } from "./foundit";
export { searchShine } from "./shine";
export { searchIndeed } from "./indeed";
export { searchLinkedInRss } from "./linkedin-rss";
export { searchWellfound } from "./wellfound";
export { searchApna } from "./apna";
export { searchCutshort } from "./cutshort";
export { searchGlassdoor } from "./glassdoor";

import { searchFoundit } from "./foundit";
import { searchShine } from "./shine";
import { searchIndeed } from "./indeed";
import { searchLinkedInRss } from "./linkedin-rss";
import { searchWellfound } from "./wellfound";
import { searchApna } from "./apna";
import { searchCutshort } from "./cutshort";
import { searchGlassdoor } from "./glassdoor";

export interface TrackerResult {
  source: string;
  jobs: TrackerJob[];
  error?: string;
}

const TRACKERS: Array<{
  name: string;
  fn: (kw: string, loc: string, env: Env) => Promise<TrackerJob[]>;
}> = [
  { name: "linkedin", fn: searchLinkedInRss },
  { name: "indeed", fn: searchIndeed },
  { name: "glassdoor", fn: searchGlassdoor },
  { name: "wellfound", fn: searchWellfound },
  { name: "foundit", fn: searchFoundit },
  { name: "shine", fn: searchShine },
  { name: "cutshort", fn: searchCutshort },
  { name: "apna", fn: searchApna },
];

/**
 * Run all trackers in parallel. Returns merged results with errors per platform.
 * Each tracker gets a 12s timeout so slow/403'd ones fail fast.
 */
export async function searchAllTrackers(
  keywords: string,
  location: string,
  env: Env,
  allowPlatforms?: string[]
): Promise<{ jobs: TrackerJob[]; platforms: Record<string, number>; errors: string[] }> {
  // Every tracker's own fetch() is now individually bounded (see
  // lib/fetch-timeout.ts), so this outer ceiling only needs to cover
  // LinkedIn's own ~16s internal fallback budget (RapidAPI + Browser
  // Rendering + plain-fetch scraping) plus a small buffer — not the old
  // unbounded worst case of a single hanging platform.
  const TRACKER_TIMEOUT = 19000;

  // LinkedIn and Foundit both use Browser Rendering to get past an
  // IP-based block — sharing one launch here means they no longer compete
  // for the account's single concurrency slot (see lib/shared-browser.ts).
  const sharedBrowser = createSharedBrowser(env);
  const envWithSharedBrowser: Env = { ...env, getSharedBrowser: sharedBrowser.get };

  const activeTrackers = allowPlatforms
    ? TRACKERS.filter((t) => allowPlatforms.includes(t.name))
    : TRACKERS;

  const results = await Promise.allSettled(
    activeTrackers.map(async (t) => {
      try {
        const jobs = await Promise.race([
          t.fn(keywords, location, envWithSharedBrowser),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error("timeout")), TRACKER_TIMEOUT)
          ),
        ]);
        return { source: t.name, jobs };
      } catch (e: any) {
        return { source: t.name, jobs: [], error: `${t.name}: ${e.message || e}` };
      }
    })
  );

  await sharedBrowser.close();

  const allJobs: TrackerJob[] = [];
  const platforms: Record<string, number> = {};
  const errors: string[] = [];

  for (const r of results) {
    if (r.status === "fulfilled") {
      const { source, jobs, error } = r.value;
      if (jobs.length) {
        platforms[source] = jobs.length;
        allJobs.push(...jobs);
      }
      if (error) errors.push(error);
    } else {
      errors.push(`Tracker failed: ${r.reason}`);
    }
  }

  return { jobs: allJobs, platforms, errors };
}
