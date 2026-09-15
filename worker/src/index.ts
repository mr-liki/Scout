import type { Env } from "./types";
import { handleOptions, corsHeaders } from "./lib/cors";
import { handleSearch } from "./routes/search";
import { handleHealth } from "./routes/health";
import { handlePlatforms } from "./routes/platforms";
import {
  handleNotifySubscribe,
  handleNotifySubscription,
  handleNotifyUnsubscribe,
} from "./routes/notify";
import {
  handleResumeCustomize,
  handleResumeScore,
} from "./routes/resume";

export default {
  // Pings every configured Glassdoor proxy instance's /health endpoint on a
  // schedule (see wrangler.toml's [triggers]) so none of them sees the ~15
  // minutes of inactivity that triggers Render's free-tier spin-down.
  // Without this, the first real search after any idle gap pays a 30-60s
  // cold-start penalty that blows past this tracker's own timeout and just
  // looks like another Glassdoor failure. This doesn't touch the separate
  // shared-IP-reputation issue (see trackers/glassdoor.ts) — it only fixes
  // cold starts.
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const urls = [env.GLASSDOOR_PROXY_URL, env.GLASSDOOR_PROXY_URL_2, env.GLASSDOOR_PROXY_URL_3].filter(
      (u): u is string => Boolean(u)
    );
    for (const url of urls) {
      ctx.waitUntil(
        fetch(`${url.replace(/\/$/, "")}/health`, { signal: AbortSignal.timeout(10000) })
          .then((r) => console.log(`[keepalive] ${url} health: ${r.status}`))
          .catch((e) => console.warn(`[keepalive] ${url} ping failed: ${e.message}`))
      );
    }
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return handleOptions(request, env);
    }

    try {
      // Route matching
      if (url.pathname === "/api/health" || url.pathname === "/health" || url.pathname === "/api/healthz") {
        return await handleHealth(request, env);
      }

      if (url.pathname === "/api/platforms") {
        return await handlePlatforms(request, env);
      }

      // /api/search — the main search endpoint (GET with q, location params)
      if (url.pathname === "/api/search") {
        return await handleSearch(request, env);
      }

      // /api/notify/* — notification subscription endpoints
      if (url.pathname === "/api/notify/subscribe") {
        return await handleNotifySubscribe(request, env);
      }
      if (url.pathname === "/api/notify/subscription") {
        return await handleNotifySubscription(request, env);
      }
      if (url.pathname === "/api/notify/unsubscribe") {
        return await handleNotifyUnsubscribe(request, env);
      }

      // /api/resume/* — AI resume customization endpoints
      if (url.pathname === "/api/resume/customize") {
        return await handleResumeCustomize(request, env);
      }
      if (url.pathname === "/api/resume/score") {
        return await handleResumeScore(request, env);
      }

      // /api/v1/quick-search — backward compat: POST body → redirect to /api/search
      if (url.pathname === "/api/v1/quick-search" && request.method === "POST") {
        try {
          const body = await request.json() as any;
          const searchUrl = new URL(request.url);
          searchUrl.pathname = "/api/search";
          searchUrl.searchParams.set("q", body.keywords || "");
          if (body.location) searchUrl.searchParams.set("location", body.location);
          if (body.limit) searchUrl.searchParams.set("limit", String(body.limit));
          const newReq = new Request(searchUrl.toString(), { method: "GET", headers: request.headers });
          return await handleSearch(newReq, env);
        } catch {
          return Response.json({ error: "Invalid request body" }, { status: 400 });
        }
      }

      // /api/v1/quick-search/platforms — backward compat
      if (url.pathname === "/api/v1/quick-search/platforms") {
        return await handlePlatforms(request, env);
      }

      // 404
      const origin = request.headers.get("Origin");
      return Response.json(
        { error: "Not found" },
        {
          status: 404,
          headers: corsHeaders(origin, env.ALLOWED_ORIGINS),
        }
      );
    } catch (e: any) {
      const origin = request.headers.get("Origin");
      return Response.json(
        { error: "Internal error", message: e.message },
        {
          status: 500,
          headers: corsHeaders(origin, env.ALLOWED_ORIGINS),
        }
      );
    }
  },
};
