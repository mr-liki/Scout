/**
 * api.js — Talks to the SCOUT Jobs backend (/api/search).
 *
 * If the backend is unreachable (GitHub Pages static hosting, offline, etc.)
 * it silently falls back to the bundled demo dataset and flags demo mode so
 * the UI can show the banner.
 */

import { demoSearch } from "./demo.js";

let _apiBase = "";            // same-origin by default (Vercel/Netlify/server.py)
let _live = null;             // null = unknown, true/false = probed
let _probePromise = null;

/** Probe once whether the live API exists (cached). */
export function probeApi() {
  if (_live !== null) return Promise.resolve(_live);
  if (_probePromise) return _probePromise;
  _probePromise = fetch(`${_apiBase}/api/health`, { signal: AbortSignal.timeout(4000) })
    .then((r) => {
      _live = r.ok;
      return _live;
    })
    .catch(() => {
      _live = false;
      return false;
    });
  return _probePromise;
}

/**
 * Search jobs. Returns { result, demo } — demo=true means the result came
 * from the fallback dataset.
 */
export async function searchJobs(keywords, location = "") {
  const live = await probeApi();
  if (live) {
    try {
      const params = new URLSearchParams({ q: keywords });
      if (location) params.set("location", location);
      const r = await fetch(`${_apiBase}/api/search?${params}`, {
        signal: AbortSignal.timeout(40000),
      });
      if (r.ok) {
        const data = await r.json();
        if (data && Array.isArray(data.jobs)) {
          return { result: data, demo: false };
        }
      }
    } catch {
      /* fall through to demo */
    }
    _live = false; // backend probed OK but search failed — use demo
  }
  return { result: demoSearch(keywords, location), demo: true };
}
