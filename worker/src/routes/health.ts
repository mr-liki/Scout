import type { Env } from "../types";
import { corsHeaders } from "../lib/cors";

export async function handleHealth(
  request: Request,
  env: Env
): Promise<Response> {
  const origin = request.headers.get("Origin");
  const headers = corsHeaders(origin, env.ALLOWED_ORIGINS);

  // Check D1 connectivity
  let dbOk = false;
  try {
    const result = await env.DB.prepare("SELECT 1").first();
    dbOk = !!result;
  } catch {}

  return Response.json(
    {
      status: dbOk ? "ok" : "degraded",
      service: "SCOUTJOBS API",
      db: dbOk ? "connected" : "disconnected",
      version: "2.0.0",
      timestamp: new Date().toISOString(),
    },
    { headers }
  );
}
