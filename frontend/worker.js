/**
 * Cloudflare Worker entrypoint for SCOUTJOBS.
 *
 * Serves the static frontend and proxies /api/* to the backend, so the
 * browser only ever talks to https://scout.apexora.workers.dev -- it never
 * sees the backend's Cloudflare Tunnel hostname (BACKEND_API_URL).
 */

// Only these headers are forwarded to the backend (and Authorization, for
// if it's ever added later) -- everything else (cookies, CF-* internal
// headers, etc.) is dropped rather than blindly relayed.
const PROXIED_REQUEST_HEADERS = ["content-type", "authorization", "accept"];

// FastAPI's health/readiness routes are NOT under /api (and this Worker
// must not change FastAPI's routes), so these two paths are aliased --
// every other /api/* path already matches a real backend route and is
// forwarded unchanged.
const HEALTH_ALIASES = {
  "/api/healthz": "/healthz",
  "/api/readyz": "/readyz",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/")) {
      return proxyToBackend(request, url, env);
    }

    return env.ASSETS.fetch(request);
  },
};

async function proxyToBackend(request, url, env) {
  const backendBase = env.BACKEND_API_URL;
  if (!backendBase) {
    return backendUnavailable();
  }

  const backendPath = HEALTH_ALIASES[url.pathname] ?? url.pathname;
  const target = new URL(backendPath + url.search, backendBase);

  const headers = new Headers();
  for (const name of PROXIED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);

  try {
    const backendResponse = await fetch(target.toString(), {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
    });
    // Response returned unchanged: same status, headers, and body stream.
    return new Response(backendResponse.body, backendResponse);
  } catch (err) {
    // Never leak the backend/tunnel URL or a stack trace to the client.
    console.error("Backend proxy error:", err && err.message);
    return backendUnavailable();
  }
}

function backendUnavailable() {
  return new Response(JSON.stringify({ error: "Backend unavailable" }), {
    status: 502,
    headers: { "Content-Type": "application/json" },
  });
}
