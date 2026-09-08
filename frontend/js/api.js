/**
 * api.js — Talks to the SCOUT Jobs backend.
 *
 * Supports both legacy /api/search and production /api/v1/searches endpoints.
 * Production uses async polling for LinkedIn searches.
 */

import { demoSearch } from "./demo.js";

// Configurable API base (set via environment or defaults to same-origin)
let _apiBase = window.SCOUTJOBS_CONFIG?.apiBase ?? "";
let _live = null;
let _probePromise = null;

/**
 * Set API base URL.
 * @param {string} base - e.g. "https://api.scoutjobs.com" or "" for same-origin
 */
export function setApiBase(base) {
  _apiBase = base || "";
}

/**
 * Probe once whether the live API exists (cached).
 */
export function probeApi() {
  if (_live !== null) return Promise.resolve(_live);
  if (_probePromise) return _probePromise;
  _probePromise = fetch(`${_apiBase}/api/healthz`, { signal: AbortSignal.timeout(4000) })
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
 * Legacy search across all platforms. Returns { result, demo }.
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
    _live = false;
  }
  return { result: demoSearch(keywords, location), demo: true };
}

/**
 * Production LinkedIn search with async polling.
 * Returns { search_id, poll_fn } for progressive job loading.
 */
export async function createLinkedInSearch(options = {}) {
  const live = await probeApi();
  if (!live) {
    return { search_id: null, poll_fn: null, demo: true };
  }

  try {
    const r = await fetch(`${_apiBase}/api/v1/searches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keywords: options.keywords || "",
        location: options.location || "",
        posted_within: options.posted_within || null,
        under_10: options.under_10 || false,
        easy_apply: options.easy_apply || false,
        sort_mode: options.sort || "newest",
        limit: options.limit || 100,
        max_pages: options.max_pages || 20,
        start: options.start || 0,
      }),
      signal: AbortSignal.timeout(10000),
    });

    if (r.ok) {
      const data = await r.json();
      return {
        search_id: data.search_id,
        poll_fn: () => pollSearch(data.search_id),
        initial_status: data.status,
      };
    }
  } catch {
    /* fall through */
  }
  return { search_id: null, poll_fn: null, demo: false };
}

/**
 * Poll search status and results.
 */
async function pollSearch(searchId) {
  if (!searchId) return null;

  try {
    const r = await fetch(`${_apiBase}/api/v1/searches/${searchId}`, {
      signal: AbortSignal.timeout(10000),
    });
    if (r.ok) {
      return await r.json();
    }
  } catch {
    /* fall through */
  }
  return null;
}

/**
 * Resume a paused/failed search.
 */
export async function resumeSearch(searchId) {
  const live = await probeApi();
  if (!live) return null;

  try {
    const r = await fetch(`${_apiBase}/api/v1/searches/${searchId}/resume`, {
      method: "POST",
      signal: AbortSignal.timeout(10000),
    });
    if (r.ok) {
      return await r.json();
    }
  } catch {
    /* fall through */
  }
  return null;
}

/**
 * Fetch lazy detail for a single LinkedIn job.
 */
export async function fetchLinkedInDetail(jobId) {
  const live = await probeApi();
  if (!live) return null;

  try {
    const r = await fetch(`${_apiBase}/api/jobs/linkedin/${jobId}`, {
      signal: AbortSignal.timeout(15000),
    });
    if (r.ok) {
      return await r.json();
    }
  } catch {
    /* fall through */
  }
  return null;
}
