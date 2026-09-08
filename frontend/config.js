/**
 * config.js — SCOUTJOBS API configuration.
 *
 * Production: leave apiBase as "" (same-origin). The Cloudflare Worker
 * (frontend/worker.js) proxies /api/* to the backend server-side, so the
 * browser never needs -- and must never be given -- the backend's tunnel
 * URL. See docs/CLOUDFLARE_API_PROXY.md.
 *
 * For local development against a backend running on a different port,
 * set apiBase to e.g. "http://localhost:8000".
 */
window.SCOUTJOBS_CONFIG = {
  apiBase: "",
};
